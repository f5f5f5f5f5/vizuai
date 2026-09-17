#!/usr/bin/env python3
"""Build furniture_search dataset from a folder of input images.

This script emulates production furniture_search flow:
  image -> Vision -> object filtering -> crop upload -> SearchAPI (WB/Ozon/YM)
  -> links per object -> numbered overlay image + metadata/debug files.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from config import Settings
from models.schemas import ProductResult, VisionObject
from services.searchapi import SearchApiService
from services.storage import S3Storage
from services.vision import GoogleVisionService
from utils.image_processing import batch_crop
from utils.label_loader import load_label_set
from utils.pdf_generator import apply_numbered_overlay
from utils.response_parser import parse_searchapi, parse_vision, searchapi_error_message

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MARKETPLACES = [
    ("ozon", "ozon.ru"),
    ("yandex_market", "market.yandex.ru"),
    ("wildberries", "wildberries.ru"),
]
MARKET_PREFIX = {
    "wildberries": "wb",
    "ozon": "ozon",
    "yandex_market": "ym",
}


@dataclass
class SampleStats:
    image_path: Path
    out_dir: Path
    objects_detected: int
    object_cards: int
    products: int


def _parse_label_list(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _normalize_input_path(raw: str) -> Path:
    text = raw.strip()
    m = re.match(r"^([A-Za-z]):[\\\\/](.+)$", text)
    if m:
        drive = m.group(1).lower()
        rest = m.group(2).replace("\\", "/")
        return Path(f"/mnt/{drive}/{rest}")
    return Path(text).expanduser()


def _iter_images(root: Path, recursive: bool) -> Iterable[Path]:
    if recursive:
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                yield path
        return
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            yield path


def _timestamp_folder_name() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H%M%S")


def _build_numbered_boxes(objects: list[VisionObject]) -> list[dict]:
    boxes: list[dict] = []
    for idx, obj in enumerate(objects, start=1):
        if not obj.bounding_box:
            continue
        xs = [vertex.x for vertex in obj.bounding_box]
        ys = [vertex.y for vertex in obj.bounding_box]
        if not xs or not ys:
            continue
        boxes.append(
            {
                "index": idx,
                "x": (min(xs) + max(xs)) / 2,
                "y": (min(ys) + max(ys)) / 2,
            }
        )
    return boxes


def _dedupe_products(products: list[ProductResult]) -> list[ProductResult]:
    seen: set[str] = set()
    unique: list[ProductResult] = []
    for item in products:
        key = item.url.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _format_furniture_summary(cards: list[dict]) -> str:
    if not cards:
        return "По фото не удалось найти подходящие товары в OZON, WB и Яндекс Маркете."
    source_labels = {"ozon": "Ozon", "wildberries": "WB", "yandex_market": "YM"}
    lines = ["Нашел подходящие позиции по объектам"]
    for card in cards:
        index = card.get("index")
        label = card.get("label") if isinstance(card.get("label"), str) else "Объект"
        links = card.get("links") if isinstance(card.get("links"), dict) else {}
        lines.append(f"<b>{index}) {html.escape(label)}</b>")
        has_any = False
        for source in ("wildberries", "ozon", "yandex_market"):
            values = links.get(source) if isinstance(links, dict) else None
            if not isinstance(values, list) or not values:
                continue
            anchors: list[str] = []
            for i, link in enumerate(values[:3], start=1):
                if not isinstance(link, str) or not link.strip():
                    continue
                anchors.append(f'<a href="{html.escape(link.strip(), quote=True)}">{i}</a>')
            if anchors:
                has_any = True
                lines.append(f"{source_labels[source]}: " + " | ".join(anchors))
        if not has_any:
            lines.append("Ссылки не найдены")
        lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _metadata_payload(objects_count: int, object_cards_count: int, products_count: int) -> dict:
    return {
        "simple_pipeline": {
            "best_label": None,
            "input_prepared": None,
            "timings_s": None,
            "scores": {"render": None, "rerender": None},
            "costs": {
                "render_usd": None,
                "rerender_usd": None,
                "ranker_usd": None,
                "image_total_usd": None,
                "image_sources": None,
            },
            "tokens": {
                "planner": None,
                "ranker": None,
                "validator": None,
                "rerender_validator": None,
            },
            "validation": {"render_ok": False, "rerender_ok": False, "best_ok": False},
            "planner_block": {"blocked": False, "reason": None, "message": None},
            "style_reference": {
                "enabled": False,
                "used": False,
                "source": None,
                "status": None,
                "prepared": None,
            },
            "ranker": {
                "best": None,
                "confidence": None,
                "both_failed": None,
                "fallback_reason": None,
            },
            "planner_parser": {"parse_mode": None, "text_fallback_used": False, "schema": None},
            "ranker_parser": {"parse_mode": None, "schema": None},
            "validator_parser": {
                "render_parse_mode": None,
                "rerender_parse_mode": None,
                "render_invalid_json": False,
                "rerender_invalid_json": False,
                "render_schema": None,
                "rerender_schema": None,
            },
        },
        "search": {
            "objects_count": objects_count,
            "object_cards_count": object_cards_count,
            "products_count": products_count,
        },
    }


def _write_metadata_debug_txt(sample_dir: Path, metadata: dict, debug: dict) -> None:
    metadata_raw = json.dumps(metadata, ensure_ascii=False)
    debug_raw = json.dumps(debug, ensure_ascii=False)
    text = (
        f'    "metadata": {json.dumps(metadata_raw, ensure_ascii=False)},\n'
        f'    "debug_json": {json.dumps(debug_raw, ensure_ascii=False)}'
    )
    (sample_dir / "metadata+debug.txt").write_text(text, encoding="utf-8")
    (sample_dir / "metadata+debug_pretty.json").write_text(
        json.dumps({"metadata": metadata, "debug_json": debug}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _search_market(
    service: SearchApiService, crop_url: str, marketplace: str, query: str
) -> tuple[str, dict, list[ProductResult]]:
    payload = await service.search(crop_url, query=query)
    err = searchapi_error_message(payload)
    if err:
        raise RuntimeError(f"{marketplace}: {err}")
    matches = parse_searchapi(payload, label="", marketplace=marketplace, limit=3)
    return marketplace, payload, matches


async def _process_image(
    *,
    image_path: Path,
    out_root: Path,
    settings: Settings,
    vision_service: GoogleVisionService,
    search_service: SearchApiService,
    storage: S3Storage,
    exclude_labels: set[str],
    generic_labels: set[str],
) -> SampleStats:
    now = datetime.now(tz=timezone.utc)
    folder = _timestamp_folder_name()
    sample_dir = out_root / folder
    suffix = 1
    while sample_dir.exists():
        suffix += 1
        sample_dir = out_root / f"{folder}_{suffix}"
    sample_dir.mkdir(parents=True, exist_ok=False)

    image_bytes = image_path.read_bytes()
    vision_payload = await vision_service.detect_objects(image_bytes)
    objects = parse_vision(
        vision_payload,
        exclude_labels=exclude_labels,
        min_score=settings.VISION_MIN_SCORE,
        min_area=settings.VISION_MIN_AREA,
        max_objects=settings.MAX_OBJECTS,
        prefetch_n=settings.VISION_PREFETCH_N,
        iou_threshold=settings.VISION_IOU_THRESHOLD,
        containment_threshold=settings.VISION_CONTAINMENT_THRESHOLD,
        max_per_label=settings.VISION_MAX_PER_LABEL,
        generic_labels=generic_labels,
        generic_iou_threshold=settings.VISION_GENERIC_IOU_THRESHOLD,
        generic_containment_threshold=settings.VISION_GENERIC_CONTAINMENT_THRESHOLD,
        global_iou_threshold=settings.VISION_DUPLICATE_IOU_THRESHOLD,
        global_containment_threshold=settings.VISION_DUPLICATE_CONTAINMENT_THRESHOLD,
    )

    crops = batch_crop(
        image_bytes,
        objects,
        image_format=(settings.CROP_IMAGE_FORMAT or "JPEG").upper().strip(),
        mask_shrink_ratio=settings.CROP_MASK_SHRINK_RATIO,
        mask_transparent=settings.CROP_MASK_TRANSPARENT,
    )

    products: list[ProductResult] = []
    object_cards: list[dict] = []
    numbered_boxes: list[dict] = []
    for crop_idx, item in enumerate(crops, start=1):
        obj = item["object"]
        crop_id = f"{int(time.time() * 1000)}{crop_idx:02d}"
        crop_file_name = f"crops_{now.strftime('%Y%m%d_%H%M%S')}-{crop_id}.jpg"
        crop_local_path = sample_dir / crop_file_name
        crop_local_path.write_bytes(item["bytes"])

        if settings.S3_PRESIGN_INPUTS:
            crop_url = await asyncio.to_thread(
                storage.upload_bytes_presigned,
                item["bytes"],
                ".jpg",
                None,
                settings.S3_PRESIGN_EXPIRES,
            )
        else:
            crop_url = await asyncio.to_thread(storage.upload_bytes, item["bytes"], ".jpg")

        links_by_market: dict[str, list[str]] = {}
        market_tasks = [
            _search_market(search_service, crop_url, marketplace, query)
            for marketplace, query in MARKETPLACES
        ]
        market_results = await asyncio.gather(*market_tasks, return_exceptions=True)
        for idx_market, result in enumerate(market_results):
            marketplace, query = MARKETPLACES[idx_market]
            raw_file = sample_dir / f"{MARKET_PREFIX[marketplace]}_{crop_id}.txt"
            if isinstance(result, Exception):
                raw_file.write_text(
                    json.dumps(
                        {
                            "status": "error",
                            "marketplace": marketplace,
                            "query": query,
                            "error": str(result),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                links_by_market[marketplace] = []
                continue

            marketplace, raw_payload, matches = result
            for match in matches:
                match.label = obj.label
            products.extend(matches)
            products = _dedupe_products(products)
            links = [m.url for m in matches]
            links_by_market[marketplace] = links
            raw_file.write_text(
                json.dumps(raw_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        has_links = any(links_by_market.get(marketplace) for marketplace, _ in MARKETPLACES)
        if not has_links:
            continue

        xs = [v.x for v in obj.bounding_box]
        ys = [v.y for v in obj.bounding_box]
        if not xs or not ys:
            continue
        marker_index = len(numbered_boxes) + 1
        numbered_boxes.append(
            {"index": marker_index, "x": (min(xs) + max(xs)) / 2, "y": (min(ys) + max(ys)) / 2}
        )
        object_cards.append(
            {
                "index": marker_index,
                "label": obj.label,
                "crop_url": crop_url,
                "crop_local_path": str(crop_local_path),
                "links": links_by_market,
            }
        )

    final_bytes = apply_numbered_overlay(image_bytes, numbered_boxes)
    final_name = f"final_{now.strftime('%Y%m%d_%H%M%S')}-{int(time.time() * 1000)}.png"
    final_path = sample_dir / final_name
    final_path.write_bytes(final_bytes)

    summary_text = _format_furniture_summary(object_cards)
    job_id = f"local-{int(time.time() * 1000)}"
    debug = {
        "job_id": job_id,
        "mode": "furniture_search",
        "units_spent": 1,
        "style_reference_enabled": False,
        "style_ref_source": "none",
        "style_ref_used": False,
        "style_ref_status": "not_requested",
        "design_id": None,
        "vision": vision_payload,
        "final_image_url": str(final_path),
        "furniture_summary": summary_text,
        "object_cards": object_cards,
        "products_count": len(products),
        "input_image_path": str(image_path),
    }
    metadata = _metadata_payload(
        objects_count=len(objects),
        object_cards_count=len(object_cards),
        products_count=len(products),
    )
    _write_metadata_debug_txt(sample_dir, metadata, debug)

    return SampleStats(
        image_path=image_path,
        out_dir=sample_dir,
        objects_detected=len(objects),
        object_cards=len(object_cards),
        products=len(products),
    )


async def _run(args: argparse.Namespace) -> None:
    input_dir = _normalize_input_path(args.input_dir)
    out_root = _normalize_input_path(args.out_root)
    input_dir = input_dir.resolve()
    out_root = out_root.resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"Input dir not found: {input_dir}")
    out_root.mkdir(parents=True, exist_ok=True)

    # Isolate from app-mode required settings in scripts context.
    os.environ["APP_MODE"] = "polling"
    os.environ.setdefault("TELEGRAM_TOKEN", "manual-script")
    settings = Settings()
    if not settings.SEARCHAPI_KEY:
        raise SystemExit("SEARCHAPI_KEY is required (.env or env var)")
    if not settings.GCS_BUCKET:
        raise SystemExit("GCS_BUCKET is required (.env or env var)")
    if not settings.CDN_URL_TEMPLATE:
        raise SystemExit("CDN_URL_TEMPLATE is required (.env or env var)")

    vision_service = GoogleVisionService(settings, max_results=settings.VISION_MAX_RESULTS)
    search_service = SearchApiService(settings)
    storage = S3Storage(settings, prefix=args.storage_crop_prefix)
    exclude_labels = load_label_set(Path(settings.EXCLUDE_LABELS_PATH))
    generic_labels = _parse_label_list(settings.VISION_GENERIC_LABELS)

    images = list(_iter_images(input_dir, recursive=args.recursive))
    if not images:
        raise SystemExit("No images found")
    if args.limit > 0:
        images = images[: args.limit]

    print(f"Found {len(images)} image(s)")
    done = 0
    for image in images:
        try:
            stats = await _process_image(
                image_path=image,
                out_root=out_root,
                settings=settings,
                vision_service=vision_service,
                search_service=search_service,
                storage=storage,
                exclude_labels=exclude_labels,
                generic_labels=generic_labels,
            )
            done += 1
            print(
                f"[{done}/{len(images)}] {image.name} -> {stats.out_dir.name} | "
                f"objects={stats.objects_detected} cards={stats.object_cards} products={stats.products}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {image}: {exc}")

    print(f"Done. processed={done}/{len(images)} out={out_root}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build furniture_search dataset from local image folder.")
    parser.add_argument("--input-dir", required=True, help="Folder with source images.")
    parser.add_argument(
        "--out-root",
        default="DUMP/research/furniture_search",
        help="Output root folder for dataset samples.",
    )
    parser.add_argument(
        "--storage-crop-prefix",
        default="crops_data/",
        help="GCS prefix for uploaded crop images (object storage path).",
    )
    parser.add_argument("--recursive", action="store_true", help="Scan input dir recursively.")
    parser.add_argument("--limit", type=int, default=0, help="Process only first N images.")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
