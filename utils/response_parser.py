"""Parsers for external API responses."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urlparse

from models.schemas import ProductResult, VisionObject, VisionVertex


def _extract_vision_objects(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        if "responses" in payload:
            responses = payload.get("responses") or []
            if responses and isinstance(responses[0], dict):
                return responses[0].get("localizedObjectAnnotations", []) or []
        if "localizedObjectAnnotations" in payload:
            return payload.get("localizedObjectAnnotations") or []
        return payload.get("objects", []) or []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _normalized_vertices(raw_vertices: Iterable[dict]) -> list[VisionVertex]:
    vertices = []
    for raw in raw_vertices:
        x = float(raw.get("x", 0.0) or 0.0)
        y = float(raw.get("y", 0.0) or 0.0)
        vertices.append(VisionVertex(x=x, y=y))
    return vertices


def _bbox_from_vertices(vertices: list[VisionVertex]) -> tuple[float, float, float, float]:
    if not vertices:
        return 0.0, 0.0, 0.0, 0.0
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    xmin, ymin, xmax, ymax = bbox
    width = max(0.0, xmax - xmin)
    height = max(0.0, ymax - ymin)
    return width * height


def parse_vision(
    payload: object,
    exclude_labels: set[str],
    min_score: float = 0.5,
    min_area: float = 0.015,
    max_objects: int = 10,
    prefetch_n: int = 30,
    iou_threshold: float = 0.85,
    containment_threshold: float = 0.90,
    max_per_label: int = 2,
    generic_labels: set[str] | None = None,
    generic_iou_threshold: float | None = None,
    generic_containment_threshold: float | None = None,
    global_iou_threshold: float | None = None,
    global_containment_threshold: float | None = None,
) -> list[VisionObject]:
    items = _extract_vision_objects(payload)
    excluded = {label.lower().strip() for label in exclude_labels}
    candidates: list[dict] = []

    for item in items:
        raw_label = str(item.get("name", "")).strip()
        label_norm = raw_label.lower()
        if not label_norm or label_norm in excluded:
            continue
        score = float(item.get("score", 0.0) or 0.0)
        vertices_raw = (
            item.get("boundingPoly", {}).get("normalizedVertices", [])
            or item.get("boundingPoly", {}).get("vertices", [])
            or []
        )
        vertices = _normalized_vertices(vertices_raw)
        bbox = _bbox_from_vertices(vertices)
        area = _bbox_area(bbox)
        if score < min_score or area < min_area:
            continue
        label_display = _normalize_label(raw_label)
        candidates.append(
            {
                "label": label_display,
                "label_norm": label_norm,
                "score": score,
                "area": area,
                "bbox": bbox,
                "vertices": vertices,
                "rank": score * area,
            }
        )

    if not candidates:
        return []

    candidates.sort(key=lambda item: item["rank"], reverse=True)
    if prefetch_n > 0:
        candidates = candidates[:prefetch_n]

    deduped = _nms_by_label(
        candidates,
        iou_threshold=iou_threshold,
        containment_threshold=containment_threshold,
    )

    if generic_labels:
        deduped = _drop_generic_overlaps(
            deduped,
            generic_labels={label.lower().strip() for label in generic_labels},
            iou_threshold=generic_iou_threshold or iou_threshold,
            containment_threshold=generic_containment_threshold or containment_threshold,
        )

    if global_iou_threshold is not None or global_containment_threshold is not None:
        deduped = _nms_global(
            deduped,
            iou_threshold=global_iou_threshold or iou_threshold,
            containment_threshold=global_containment_threshold or containment_threshold,
        )

    deduped.sort(key=lambda item: item["rank"], reverse=True)
    if max_per_label > 0:
        counts: dict[str, int] = {}
        limited: list[dict] = []
        for item in deduped:
            label_norm = item["label_norm"]
            count = counts.get(label_norm, 0)
            if count >= max_per_label:
                continue
            counts[label_norm] = count + 1
            limited.append(item)
    else:
        limited = deduped

    limited.sort(key=lambda item: item["rank"], reverse=True)
    selected = limited[:max_objects] if max_objects > 0 else limited

    results: list[VisionObject] = []
    for item in selected:
        results.append(
            VisionObject(
                label=item["label"],
                score=item["score"],
                area=item["area"],
                bounding_box=item["vertices"],
            )
        )
    return results


def _normalize_label(label: str) -> str:
    cleaned = label.strip()
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    if "table" in lowered:
        return "Table"
    return cleaned


def _nms_by_label(
    candidates: list[dict],
    iou_threshold: float,
    containment_threshold: float,
) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in candidates:
        grouped.setdefault(item["label_norm"], []).append(item)
    kept: list[dict] = []
    for items in grouped.values():
        items.sort(key=lambda item: item["rank"], reverse=True)
        while items:
            best = items.pop(0)
            kept.append(best)
            remaining: list[dict] = []
            for cand in items:
                if _suppress_pair(best, cand, iou_threshold, containment_threshold):
                    continue
                remaining.append(cand)
            items = remaining
    return kept


def _nms_global(
    candidates: list[dict],
    iou_threshold: float,
    containment_threshold: float,
) -> list[dict]:
    items = sorted(candidates, key=lambda item: item["rank"], reverse=True)
    kept: list[dict] = []
    while items:
        best = items.pop(0)
        kept.append(best)
        remaining: list[dict] = []
        for cand in items:
            if _suppress_pair(best, cand, iou_threshold, containment_threshold):
                continue
            remaining.append(cand)
        items = remaining
    return kept


def _suppress_pair(
    left: dict, right: dict, iou_threshold: float, containment_threshold: float
) -> bool:
    iou = _bbox_iou(left["bbox"], right["bbox"])
    if iou > iou_threshold:
        return True
    containment = _bbox_containment(left["bbox"], right["bbox"])
    return containment > containment_threshold


def _bbox_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    inter = _bbox_intersection_area(a, b)
    if inter <= 0:
        return 0.0
    union = _bbox_area(a) + _bbox_area(b) - inter
    return inter / union if union > 0 else 0.0


def _bbox_containment(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    inter = _bbox_intersection_area(a, b)
    if inter <= 0:
        return 0.0
    min_area = min(_bbox_area(a), _bbox_area(b))
    return inter / min_area if min_area > 0 else 0.0


def _bbox_intersection_area(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    return inter_w * inter_h


def _drop_generic_overlaps(
    candidates: list[dict],
    generic_labels: set[str],
    iou_threshold: float,
    containment_threshold: float,
) -> list[dict]:
    candidates = sorted(candidates, key=lambda item: item["rank"], reverse=True)
    kept: list[dict] = []
    for item in candidates:
        is_generic = item["label_norm"] in generic_labels
        if is_generic:
            if any(
                (other["label_norm"] not in generic_labels)
                and _suppress_pair(other, item, iou_threshold, containment_threshold)
                for other in kept
            ):
                continue
            kept.append(item)
            continue
        kept = [
            other
            for other in kept
            if not (
                other["label_norm"] in generic_labels
                and _suppress_pair(item, other, iou_threshold, containment_threshold)
            )
        ]
        kept.append(item)
    return kept


def _extract_candidates(payload: dict) -> list[dict]:
    for key in ("results", "visual_matches", "items", "organic_results", "matches"):
        candidates = payload.get(key)
        if isinstance(candidates, list):
            return [item for item in candidates if isinstance(item, dict)]
    return []


def searchapi_candidate_source(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("results", "visual_matches", "items", "organic_results", "matches"):
        candidates = payload.get(key)
        if isinstance(candidates, list):
            return key
    return None


def searchapi_visual_matches_count(payload: dict) -> int:
    if not isinstance(payload, dict):
        return 0
    value = payload.get("visual_matches")
    if not isinstance(value, list):
        return 0
    return len([item for item in value if isinstance(item, dict)])


def searchapi_candidate_samples(payload: dict, limit: int = 3) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        return []
    limit = max(int(limit or 0), 0)
    if limit == 0:
        return []
    samples: list[dict[str, object]] = []
    for item in _extract_candidates(payload)[:limit]:
        if not isinstance(item, dict):
            continue
        image = item.get("image")
        thumbnail = item.get("thumbnail")
        samples.append(
            {
                "keys": sorted(str(key) for key in item.keys()),
                "has_image": image is not None,
                "image_type": type(image).__name__ if image is not None else None,
                "image_keys": (
                    sorted(str(key) for key in image.keys())[:20]
                    if isinstance(image, dict)
                    else []
                ),
                "has_thumbnail": thumbnail is not None,
                "thumbnail_type": type(thumbnail).__name__ if thumbnail is not None else None,
            }
        )
    return samples


def _candidate_url(candidate: dict) -> str:
    for key in ("link", "url", "source", "website", "redirected_link"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _candidate_title(candidate: dict) -> str:
    for key in ("title", "name", "snippet"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _candidate_image_url(candidate: dict) -> str:
    for key in (
        "thumbnail",
        "image",
        "thumbnail_url",
        "image_url",
        "thumbnailUrl",
        "imageUrl",
        "product_image",
        "thumbnails",
        "images",
    ):
        value = candidate.get(key)
        url = _extract_http_url(value)
        if url:
            return url

    # SearchAPI can nest image links in image-* structured blobs.
    for key, value in candidate.items():
        key_norm = str(key).lower()
        if not any(token in key_norm for token in ("image", "thumb", "photo", "picture")):
            continue
        url = _extract_http_url(value)
        if url:
            return url
    return ""


def _extract_http_url(value: object) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("https://", "http://")):
            return text
        return ""
    if isinstance(value, dict):
        for key in (
            "thumbnail_url",
            "url",
            "link",
            "source",
            "src",
            "small",
            "image_url",
            "original",
            "large",
            "value",
        ):
            nested = value.get(key)
            found = _extract_http_url(nested)
            if found:
                return found
        for nested in value.values():
            found = _extract_http_url(nested)
            if found:
                return found
        return ""
    if isinstance(value, list):
        for item in value:
            found = _extract_http_url(item)
            if found:
                return found
    return ""


def _is_marketplace_url(url: str, marketplace: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path.lower()
    if marketplace == "ozon":
        if "ozon.ru" not in netloc:
            return False
        if path.startswith("/travel/"):
            return False
        return path.startswith("/product/") or path.startswith("/p/")
    if marketplace == "wildberries":
        if "wildberries.ru" not in netloc:
            return False
        return "/catalog/" in path and path.endswith("/detail.aspx")
    if marketplace == "yandex_market":
        if "market.yandex.ru" not in netloc:
            return False
        return "/product--" in path or "/product/" in path or "/offer/" in path or "/card/" in path
    return False


def _normalize_marketplace_url(url: str, marketplace: str) -> str:
    if marketplace != "yandex_market":
        return url
    parsed = urlparse(url)
    path = parsed.path or ""
    lowered = path.lower()
    for suffix in ("/reviews", "/reviews/", "/questions", "/questions/"):
        if lowered.endswith(suffix):
            path = path[: -len(suffix)]
            break
    if path and not path.endswith("/"):
        path += "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


@dataclass(frozen=True)
class SearchCandidate:
    label: str
    source: str
    url: str
    title: str
    image_url: str | None
    position: int
    token_score: float = 0.0
    include_match: bool = False


def extract_searchapi_candidates(
    payload: dict,
    label: str,
    marketplace: str,
    limit: int = 60,
) -> list[SearchCandidate]:
    if not isinstance(payload, dict):
        return []
    results: list[SearchCandidate] = []
    seen: set[str] = set()
    for index, candidate in enumerate(_extract_candidates(payload), start=1):
        url = _candidate_url(candidate)
        if not _is_marketplace_url(url, marketplace):
            continue
        url = _normalize_marketplace_url(url, marketplace)
        normalized = url.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        results.append(
            SearchCandidate(
                label=label,
                source=marketplace,
                url=url,
                title=_candidate_title(candidate),
                image_url=_candidate_image_url(candidate) or None,
                position=index,
            )
        )
        if limit > 0 and len(results) >= limit:
            break
    return results


def rank_searchapi_candidates(
    candidates: list[SearchCandidate],
    include_tokens: list[str] | tuple[str, ...] | None = None,
    exclude_tokens: list[str] | tuple[str, ...] | None = None,
    limit: int | None = None,
) -> list[SearchCandidate]:
    include = _normalize_tokens(include_tokens)
    exclude = _normalize_tokens(exclude_tokens)
    included: list[SearchCandidate] = []
    remainder: list[SearchCandidate] = []
    for item in candidates:
        title = (item.title or "").lower()
        url = (item.url or "").lower()
        joined = f"{title} {url}"
        if exclude and any(token in joined for token in exclude):
            continue

        include_title = bool(include and any(token in title for token in include))
        include_url = bool(include and any(token in url for token in include))
        include_match = include_title or include_url

        score = 1.0 if include_match else 0.0
        # Position is the main prior; score only tracks include/non-include.
        score -= min(max(item.position, 1), 10_000) / 100_000.0
        candidate = SearchCandidate(
            label=item.label,
            source=item.source,
            url=item.url,
            title=item.title,
            image_url=item.image_url,
            position=item.position,
            token_score=score,
            include_match=include_match,
        )
        if include_match:
            included.append(candidate)
        else:
            remainder.append(candidate)

    included.sort(key=lambda candidate: candidate.position)
    remainder.sort(key=lambda candidate: candidate.position)
    ranked = included + remainder
    if isinstance(limit, int) and limit > 0:
        return ranked[:limit]
    return ranked


def _normalize_tokens(tokens: list[str] | tuple[str, ...] | None) -> list[str]:
    if not tokens:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if not isinstance(token, str):
            continue
        value = token.strip().lower()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def parse_searchapi(
    payload: dict, label: str, marketplace: str, limit: int = 3
) -> list[ProductResult]:
    candidates = extract_searchapi_candidates(
        payload=payload,
        label=label,
        marketplace=marketplace,
        limit=max(limit * 10, 30),
    )
    ranked = rank_searchapi_candidates(candidates=candidates, limit=limit)
    return [
        ProductResult(label=item.label, url=item.url, source=item.source)
        for item in ranked
    ]


def searchapi_error_message(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Invalid SearchAPI payload"
    error_value = payload.get("error")
    if error_value:
        if isinstance(error_value, dict):
            message = error_value.get("message") or error_value.get("error") or error_value.get("type")
            return str(message or error_value)
        return str(error_value)
    errors = payload.get("errors")
    if isinstance(errors, list) and errors:
        return "; ".join(str(item) for item in errors)
    if payload.get("status") in {"error", "failed"}:
        return str(payload.get("message") or payload.get("status") or "SearchAPI error")
    if payload.get("success") is False:
        return str(payload.get("message") or "SearchAPI error")
    return None
