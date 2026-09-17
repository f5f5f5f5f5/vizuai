"""LLM vision verifier for furniture search candidates."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp

from config import Settings


_ALLOWED_VERBOSITY_VALUES = {"low", "medium", "high"}


@dataclass(frozen=True)
class VerifierCandidate:
    candidate_id: int
    marketplace: str
    title: str
    url: str
    image_url: str | None
    token_score: float
    token_rank: int


@dataclass(frozen=True)
class VisionVerifierResult:
    top_ids_by_market: dict[str, list[int]]
    score_by_id: dict[int, int]
    raw: dict[str, Any]
    usage: dict[str, Any] | None
    cost_usd: float | None
    cost_source: str | None


@dataclass(frozen=True)
class VisionVerifierDebugInfo:
    failure_reason: str | None
    prepared_candidates_total: int
    prepared_candidates_by_market: dict[str, int]
    model_attempts: list[dict[str, Any]]
    response_preview: str | None
    input_candidates_total: int = 0
    input_candidates_with_image_url: int = 0
    input_candidates_with_image_url_by_market: dict[str, int] | None = None
    download_success_total: int = 0
    download_success_by_market: dict[str, int] | None = None
    download_fail_reason_counts: dict[str, int] | None = None
    download_fail_reason_counts_by_market: dict[str, dict[str, int]] | None = None


class FurnitureVisionVerifier:
    def __init__(
        self,
        settings: Settings,
        logger: logging.Logger | None = None,
        image_fetch_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self._settings = settings
        self._logger = logger or logging.getLogger("pipeline")
        self._image_fetch_semaphore = image_fetch_semaphore
        verbosity = str(settings.FURNITURE_VERIFIER_TEXT_VERBOSITY or "medium").strip().lower()
        if verbosity not in _ALLOWED_VERBOSITY_VALUES:
            verbosity = "medium"
        self._text_verbosity = verbosity
        prompt_path = Path(settings.FURNITURE_VISION_VERIFIER_PROMPT_PATH)
        if not prompt_path.exists():
            raise FileNotFoundError(f"Furniture verifier prompt not found: {prompt_path}")
        self._system_prompt = prompt_path.read_text(encoding="utf-8").strip()

    async def verify(
        self,
        *,
        crop_bytes: bytes,
        crop_id: str,
        expected_type: str,
        candidates_by_market: dict[str, list[VerifierCandidate]],
    ) -> VisionVerifierResult | None:
        result, _ = await self.verify_with_debug(
            crop_bytes=crop_bytes,
            crop_id=crop_id,
            expected_type=expected_type,
            candidates_by_market=candidates_by_market,
        )
        return result

    async def verify_with_debug(
        self,
        *,
        crop_bytes: bytes,
        crop_id: str,
        expected_type: str,
        candidates_by_market: dict[str, list[VerifierCandidate]],
    ) -> tuple[VisionVerifierResult | None, VisionVerifierDebugInfo]:
        if not self._settings.FURNITURE_VERIFIER_ENABLED:
            return None, VisionVerifierDebugInfo(
                failure_reason="disabled",
                prepared_candidates_total=0,
                prepared_candidates_by_market={},
                model_attempts=[],
                response_preview=None,
            )
        if not self._settings.OPENAI_API_KEY:
            return None, VisionVerifierDebugInfo(
                failure_reason="missing_openai_api_key",
                prepared_candidates_total=0,
                prepared_candidates_by_market={},
                model_attempts=[],
                response_preview=None,
            )
        if not self._system_prompt:
            return None, VisionVerifierDebugInfo(
                failure_reason="missing_prompt",
                prepared_candidates_total=0,
                prepared_candidates_by_market={},
                model_attempts=[],
                response_preview=None,
            )

        input_candidates_total = 0
        input_candidates_with_image_url = 0
        input_candidates_with_image_url_by_market: dict[str, int] = {}
        for market, candidates in candidates_by_market.items():
            input_candidates_total += len(candidates)
            count = 0
            for candidate in candidates:
                if candidate.image_url:
                    count += 1
                    input_candidates_with_image_url += 1
            if count > 0:
                input_candidates_with_image_url_by_market[market] = count

        prepared, download_debug = await self._prepare_candidates(candidates_by_market)
        prepared_by_market: dict[str, int] = {}
        for item in prepared:
            market = str(item.get("marketplace") or "").strip()
            if not market:
                continue
            prepared_by_market[market] = prepared_by_market.get(market, 0) + 1
        if not prepared:
            return None, VisionVerifierDebugInfo(
                failure_reason="no_candidate_images",
                prepared_candidates_total=0,
                prepared_candidates_by_market={},
                model_attempts=[],
                response_preview=None,
                input_candidates_total=input_candidates_total,
                input_candidates_with_image_url=input_candidates_with_image_url,
                input_candidates_with_image_url_by_market=input_candidates_with_image_url_by_market,
                download_success_total=int(download_debug.get("success_total") or 0),
                download_success_by_market=dict(download_debug.get("success_by_market") or {}),
                download_fail_reason_counts=dict(download_debug.get("fail_reason_counts") or {}),
                download_fail_reason_counts_by_market=dict(
                    download_debug.get("fail_reason_counts_by_market") or {}
                ),
            )

        metadata = self._build_metadata(crop_id=crop_id, expected_type=expected_type, prepared=prepared)
        result: dict[str, Any] | None = None
        model_attempts: list[dict[str, Any]] = []
        response_preview: str | None = None
        failure_reason: str | None = None
        for model in _build_model_candidates(
            primary=self._settings.FURNITURE_VERIFIER_MODEL,
            fallback=self._settings.FURNITURE_VERIFIER_FALLBACK_MODEL,
        ):
            result, attempt_info = await self._request_llm_detailed(
                model=model,
                crop_bytes=crop_bytes,
                metadata=metadata,
                prepared=prepared,
            )
            model_attempts.append(attempt_info)
            if attempt_info.get("response_preview"):
                response_preview = str(attempt_info.get("response_preview"))
            failure_reason = str(attempt_info.get("failure_reason") or "") or failure_reason
            if result is not None:
                break
        if result is None:
            return None, VisionVerifierDebugInfo(
                failure_reason=failure_reason or "request_failed_or_invalid_json",
                prepared_candidates_total=len(prepared),
                prepared_candidates_by_market=prepared_by_market,
                model_attempts=model_attempts,
                response_preview=response_preview,
                input_candidates_total=input_candidates_total,
                input_candidates_with_image_url=input_candidates_with_image_url,
                input_candidates_with_image_url_by_market=input_candidates_with_image_url_by_market,
                download_success_total=int(download_debug.get("success_total") or 0),
                download_success_by_market=dict(download_debug.get("success_by_market") or {}),
                download_fail_reason_counts=dict(download_debug.get("fail_reason_counts") or {}),
                download_fail_reason_counts_by_market=dict(
                    download_debug.get("fail_reason_counts_by_market") or {}
                ),
            )

        parsed_payload = result.get("parsed") if isinstance(result.get("parsed"), dict) else {}
        top_ids_by_market, score_by_id = _extract_ranked_ids(
            metadata=metadata,
            parsed=parsed_payload,
        )
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else None
        cost_usd, cost_source = _compute_verifier_cost(
            usage=usage,
            input_price_per_million=self._settings.FURNITURE_VERIFIER_INPUT_PRICE_PER_MILLION,
            output_price_per_million=self._settings.FURNITURE_VERIFIER_OUTPUT_PRICE_PER_MILLION,
        )
        return (
            VisionVerifierResult(
                top_ids_by_market=top_ids_by_market,
                score_by_id=score_by_id,
                raw=parsed_payload if isinstance(parsed_payload, dict) else {},
                usage=usage,
                cost_usd=cost_usd,
                cost_source=cost_source,
            ),
            VisionVerifierDebugInfo(
                failure_reason=None,
                prepared_candidates_total=len(prepared),
                prepared_candidates_by_market=prepared_by_market,
                model_attempts=model_attempts,
                response_preview=response_preview,
                input_candidates_total=input_candidates_total,
                input_candidates_with_image_url=input_candidates_with_image_url,
                input_candidates_with_image_url_by_market=input_candidates_with_image_url_by_market,
                download_success_total=int(download_debug.get("success_total") or 0),
                download_success_by_market=dict(download_debug.get("success_by_market") or {}),
                download_fail_reason_counts=dict(download_debug.get("fail_reason_counts") or {}),
                download_fail_reason_counts_by_market=dict(
                    download_debug.get("fail_reason_counts_by_market") or {}
                ),
            ),
        )

    async def _prepare_candidates(
        self,
        candidates_by_market: dict[str, list[VerifierCandidate]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        success_by_market: dict[str, int] = {}
        fail_reason_counts: dict[str, int] = {}
        fail_reason_counts_by_market: dict[str, dict[str, int]] = {}
        timeout = aiohttp.ClientTimeout(total=self._settings.FURNITURE_VERIFIER_IMAGE_FETCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            tasks: list[
                tuple[str, VerifierCandidate, asyncio.Task[tuple[bytes | None, str | None]]]
            ] = []
            for market, candidates in candidates_by_market.items():
                for candidate in candidates:
                    image_url = candidate.image_url
                    if not image_url:
                        continue
                    task = asyncio.create_task(
                        self._download_image_with_limit(
                            session,
                            image_url,
                        )
                    )
                    tasks.append((market, candidate, task))

            for market, candidate, task in tasks:
                image_bytes, fail_reason = await task
                if not image_bytes:
                    reason = str(fail_reason or "unknown")
                    fail_reason_counts[reason] = fail_reason_counts.get(reason, 0) + 1
                    by_market = fail_reason_counts_by_market.setdefault(market, {})
                    by_market[reason] = by_market.get(reason, 0) + 1
                    continue
                success_by_market[market] = success_by_market.get(market, 0) + 1
                prepared.append(
                    {
                        "marketplace": market,
                        "candidate": candidate,
                        "image_bytes": image_bytes,
                    }
                )
        return (
            prepared,
            {
                "success_total": sum(success_by_market.values()),
                "success_by_market": success_by_market,
                "fail_reason_counts": fail_reason_counts,
                "fail_reason_counts_by_market": fail_reason_counts_by_market,
            },
        )

    async def _download_image_with_limit(
        self,
        session: aiohttp.ClientSession,
        image_url: str,
    ) -> tuple[bytes | None, str | None]:
        attempts = max(int(self._settings.FURNITURE_VERIFIER_IMAGE_FETCH_ATTEMPTS or 1), 1)
        if self._image_fetch_semaphore is None:
            return await _download_image_bytes(session, image_url, attempts=attempts)
        async with self._image_fetch_semaphore:
            return await _download_image_bytes(session, image_url, attempts=attempts)

    def _build_metadata(
        self,
        *,
        crop_id: str,
        expected_type: str,
        prepared: list[dict[str, Any]],
    ) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in prepared:
            market = str(item["marketplace"])
            candidate: VerifierCandidate = item["candidate"]
            grouped.setdefault(market, []).append(
                {
                    "candidate_id": int(candidate.candidate_id),
                    "title": candidate.title,
                    "url": candidate.url,
                }
            )
        markets = [
            {"marketplace": market, "candidates": candidates}
            for market, candidates in grouped.items()
        ]
        return {
            "crop_id": crop_id,
            "expected_type": expected_type,
            "markets": markets,
        }

    async def _request_llm_detailed(
        self,
        *,
        model: str,
        crop_bytes: bytes,
        metadata: dict[str, Any],
        prepared: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        url = "https://api.openai.com/v1/responses"
        headers = {
            "Authorization": f"Bearer {self._settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        metadata_json = json.dumps(metadata, ensure_ascii=False)
        timeout = aiohttp.ClientTimeout(total=self._settings.FURNITURE_VERIFIER_TIMEOUT)
        attempts = 2
        error_messages: list[str] = []
        for attempt in range(1, attempts + 1):
            user_content: list[dict[str, Any]] = [
                {
                    "type": "input_text",
                    "text": f"metadata_json:\n{metadata_json}",
                },
                {
                    "type": "input_text",
                    "text": (
                        f"CROP crop_id={metadata['crop_id']} expected_type={metadata['expected_type']}"
                    ),
                },
                _image_part(crop_bytes, detail=self._settings.FURNITURE_VERIFIER_IMAGE_DETAIL),
            ]
            for item in prepared:
                candidate: VerifierCandidate = item["candidate"]
                user_content.append(
                    {
                        "type": "input_text",
                        "text": (
                            f"CANDIDATE candidate_id={candidate.candidate_id} "
                            f"marketplace={candidate.marketplace}"
                        ),
                    }
                )
                user_content.append(
                    _image_part(
                        item["image_bytes"],
                        detail=self._settings.FURNITURE_VERIFIER_IMAGE_DETAIL,
                    )
                )
            if attempt > 1:
                user_content.append(
                    {
                        "type": "input_text",
                        "text": "IMPORTANT: Return ONLY one valid JSON object that matches schema",
                    }
                )
            payload: dict[str, Any] = {
                "model": model,
                "input": [
                    {
                        "role": "system",
                        "content": [{"type": "input_text", "text": self._system_prompt}],
                    },
                    {"role": "user", "content": user_content},
                ],
                "max_output_tokens": self._settings.FURNITURE_VERIFIER_MAX_OUTPUT_TOKENS,
                "text": {
                    "format": _verifier_schema_payload(),
                    "verbosity": _resolve_verbosity_for_model(
                        model=model,
                        requested=self._text_verbosity,
                    ),
                },
                "store": False,
            }
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as response:
                        if response.status >= 400:
                            error_text = await response.text()
                            raise RuntimeError(
                                f"OpenAI verifier error {response.status}: {error_text}"
                            )
                        raw = await response.json()
            except Exception as exc:
                error_messages.append(str(exc))
                if attempt >= attempts:
                    self._logger.warning("Furniture verifier failed model=%s: %s", model, exc)
                    return None, {
                        "model": model,
                        "attempts": attempt,
                        "failure_reason": "request_failed",
                        "error": (str(exc).strip() or repr(exc)),
                    }
                await asyncio.sleep(0.6)
                continue

            text = _extract_openai_text(raw)
            parsed = _parse_json_or_none(text)
            if isinstance(parsed, dict):
                return (
                    {"parsed": parsed, "usage": raw.get("usage")},
                    {
                        "model": model,
                        "attempts": attempt,
                        "failure_reason": None,
                    },
                )
            if attempt >= attempts:
                self._logger.warning(
                    "Furniture verifier invalid JSON after retries model=%s chars=%s",
                    model,
                    len(text or ""),
                )
                return None, {
                    "model": model,
                    "attempts": attempt,
                    "failure_reason": "invalid_json",
                    "response_preview": (text or "")[:300],
                }
        return None, {
            "model": model,
            "attempts": attempts,
            "failure_reason": "request_failed_or_invalid_json",
            "error": "; ".join(error_messages[:2]) if error_messages else None,
        }


def _build_model_candidates(primary: str, fallback: str | None) -> list[str]:
    models: list[str] = []
    for raw in (primary, fallback or ""):
        model = str(raw or "").strip()
        if not model:
            continue
        if model not in models:
            models.append(model)
    return models


def _resolve_verbosity_for_model(*, model: str, requested: str) -> str:
    value = str(requested or "medium").strip().lower()
    if value not in _ALLOWED_VERBOSITY_VALUES:
        value = "medium"
    if model.startswith("gpt-4.1") and value == "low":
        return "medium"
    return value


def _verifier_schema_payload() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "furniture_vision_verifier",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "markets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "marketplace": {"type": "string"},
                            "candidates": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "candidate_id": {"type": "integer"},
                                        "title": {"type": "string"},
                                        "is_same_category": {"type": "boolean"},
                                        "is_accessory_or_decor": {"type": "boolean"},
                                        "match_score": {"type": "integer"},
                                        "reason_short": {"type": "string"},
                                    },
                                    "required": [
                                        "candidate_id",
                                        "title",
                                        "is_same_category",
                                        "is_accessory_or_decor",
                                        "match_score",
                                        "reason_short",
                                    ],
                                },
                            },
                            "top3_candidate_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                            },
                        },
                        "required": ["marketplace", "candidates", "top3_candidate_ids"],
                    },
                },
                "notes": {"type": "string"},
            },
            "required": ["markets", "notes"],
        },
    }


async def _download_image_bytes(
    session: aiohttp.ClientSession,
    url: str,
    *,
    attempts: int = 2,
) -> tuple[bytes | None, str | None]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    retryable_statuses = {408, 425, 429, 500, 502, 503, 504}
    attempts = max(int(attempts or 1), 1)
    last_reason: str | None = None
    for attempt in range(1, attempts + 1):
        try:
            async with session.get(url, headers=headers, allow_redirects=True) as response:
                if response.status >= 400:
                    last_reason = f"http_{response.status}"
                    if response.status in retryable_statuses and attempt < attempts:
                        await asyncio.sleep(0.25 * attempt)
                        continue
                    return None, last_reason
                content_type = str(response.headers.get("Content-Type") or "").lower()
                data = await response.read()
                if not data or len(data) > 10 * 1024 * 1024:
                    last_reason = "too_large_or_empty"
                    if attempt < attempts:
                        await asyncio.sleep(0.25 * attempt)
                        continue
                    return None, last_reason
                if content_type and not content_type.startswith("image/") and not _looks_like_image_bytes(data):
                    last_reason = "not_image_payload"
                    if attempt < attempts:
                        await asyncio.sleep(0.25 * attempt)
                        continue
                    return None, last_reason
                return data, None
        except asyncio.TimeoutError:
            last_reason = "timeout"
            if attempt < attempts:
                await asyncio.sleep(0.25 * attempt)
                continue
            return None, last_reason
        except Exception as exc:
            last_reason = f"exception_{type(exc).__name__}"
            if attempt < attempts:
                await asyncio.sleep(0.25 * attempt)
                continue
            return None, last_reason
    return None, (last_reason or "unknown")


def _looks_like_image_bytes(data: bytes) -> bool:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):  # PNG
        return True
    if data.startswith(b"\xff\xd8\xff"):  # JPEG
        return True
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):  # GIF
        return True
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":  # WEBP
        return True
    return False


def _image_part(image_bytes: bytes, *, detail: str = "low") -> dict[str, Any]:
    mime = "image/png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return {
        "type": "input_image",
        "image_url": f"data:{mime};base64,{encoded}",
        "detail": detail,
    }


def _extract_openai_text(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            contents = item.get("content")
            if not isinstance(contents, list):
                continue
            for content in contents:
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text.strip()
    return ""


def _parse_json_or_none(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except Exception:
            return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _extract_ranked_ids(
    *,
    metadata: dict[str, Any],
    parsed: dict[str, Any],
) -> tuple[dict[str, list[int]], dict[int, int]]:
    expected: dict[str, list[int]] = {}
    for market in metadata.get("markets", []):
        if not isinstance(market, dict):
            continue
        marketplace = market.get("marketplace")
        candidates = market.get("candidates")
        if not isinstance(marketplace, str) or not isinstance(candidates, list):
            continue
        ids = [int(item["candidate_id"]) for item in candidates if isinstance(item, dict) and "candidate_id" in item]
        expected[marketplace] = ids

    score_by_id: dict[int, int] = {}
    top_ids_by_market: dict[str, list[int]] = {market: [] for market in expected}
    parsed_markets = parsed.get("markets")
    if not isinstance(parsed_markets, list):
        return top_ids_by_market, score_by_id

    for market in parsed_markets:
        if not isinstance(market, dict):
            continue
        marketplace = market.get("marketplace")
        if not isinstance(marketplace, str) or marketplace not in expected:
            continue
        expected_ids = set(expected[marketplace])
        candidates = market.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                candidate_id = candidate.get("candidate_id")
                if not isinstance(candidate_id, int) or candidate_id not in expected_ids:
                    continue
                score = candidate.get("match_score")
                if isinstance(score, int):
                    score_by_id[candidate_id] = max(0, min(100, score))
        top_ids = market.get("top3_candidate_ids")
        if isinstance(top_ids, list):
            filtered = [
                candidate_id
                for candidate_id in top_ids
                if isinstance(candidate_id, int) and candidate_id in expected_ids
            ]
            top_ids_by_market[marketplace] = filtered[:3]

    for marketplace, ids in expected.items():
        if top_ids_by_market.get(marketplace):
            continue
        fallback = sorted(
            ids,
            key=lambda candidate_id: score_by_id.get(candidate_id, -1),
            reverse=True,
        )
        top_ids_by_market[marketplace] = fallback[:3]
    return top_ids_by_market, score_by_id


def _compute_verifier_cost(
    *,
    usage: dict[str, Any] | None,
    input_price_per_million: float | None,
    output_price_per_million: float | None,
) -> tuple[float | None, str | None]:
    payload = usage or {}
    explicit_cost = _to_float_or_none(payload.get("cost_usd") or payload.get("total_cost_usd"))
    if explicit_cost is not None and explicit_cost >= 0:
        return explicit_cost, "usage_cost_field"

    input_tokens = _to_float_or_none(payload.get("input_tokens"))
    output_tokens = _to_float_or_none(payload.get("output_tokens"))
    if (
        input_tokens is not None
        and output_tokens is not None
        and isinstance(input_price_per_million, (int, float))
        and isinstance(output_price_per_million, (int, float))
    ):
        computed = (
            (input_tokens / 1_000_000) * float(input_price_per_million)
            + (output_tokens / 1_000_000) * float(output_price_per_million)
        )
        return computed, "usage_tokens"
    return None, None


def _to_float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except Exception:
            return None
    return None
