"""LLM batch step for furniture query terms and display names."""
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
_DELETE_MARKER = "__DELETE__"


@dataclass(frozen=True)
class QueryTermsCropInput:
    crop_id: str
    vision_label: str
    image_bytes: bytes


@dataclass(frozen=True)
class QueryTermsCropResult:
    crop_id: str
    display_name_ru: str
    query_terms: tuple[str, ...]


@dataclass(frozen=True)
class QueryTermsBatchResult:
    results_by_crop: dict[str, QueryTermsCropResult]
    raw: dict[str, Any]
    usage: dict[str, Any] | None
    cost_usd: float | None
    cost_source: str | None
    provider: str
    model: str


def is_delete_marker(display_name_ru: str | None) -> bool:
    return str(display_name_ru or "").strip().upper() == _DELETE_MARKER


class FurnitureQueryTermsService:
    def __init__(self, settings: Settings, logger: logging.Logger | None = None) -> None:
        self._settings = settings
        self._logger = logger or logging.getLogger("pipeline")
        verbosity = str(settings.FURNITURE_QUERY_TERMS_TEXT_VERBOSITY or "medium").strip().lower()
        if verbosity not in _ALLOWED_VERBOSITY_VALUES:
            verbosity = "medium"
        self._text_verbosity = verbosity
        prompt_path = Path(settings.FURNITURE_QUERY_TERMS_PROMPT_PATH)
        if not prompt_path.exists():
            raise FileNotFoundError(f"Furniture query terms prompt not found: {prompt_path}")
        self._system_prompt = prompt_path.read_text(encoding="utf-8").strip()

    async def infer(
        self,
        *,
        crops: list[QueryTermsCropInput],
    ) -> QueryTermsBatchResult | None:
        if not self._settings.FURNITURE_QUERY_TERMS_ENABLED:
            return None
        if not self._settings.OPENAI_API_KEY:
            return None
        if not self._system_prompt:
            return None
        if not crops:
            return None

        expected_ids = {
            str(item.crop_id).strip()
            for item in crops
            if str(item.crop_id).strip()
        }
        if not expected_ids:
            return None

        model_candidates = _build_model_candidates(
            primary=self._settings.FURNITURE_QUERY_TERMS_MODEL,
            fallback=self._settings.FURNITURE_QUERY_TERMS_FALLBACK_MODEL,
        )
        if not model_candidates:
            return None

        metadata = {
            "crops": [
                {
                    "crop_id": str(item.crop_id),
                    "vision_label": str(item.vision_label or ""),
                }
                for item in crops
            ]
        }
        metadata_json = json.dumps(metadata, ensure_ascii=False)

        for model in model_candidates:
            parsed, usage = await self._request_llm(
                model=model,
                metadata_json=metadata_json,
                crops=crops,
            )
            if not isinstance(parsed, dict):
                continue
            normalized = _normalize_results(parsed, expected_ids=expected_ids)
            if not normalized:
                self._logger.warning(
                    "Furniture query terms parsed but empty after normalization model=%s",
                    model,
                )
                continue
            cost_usd, cost_source = _compute_cost(
                usage=usage,
                input_price_per_million=self._settings.FURNITURE_QUERY_TERMS_INPUT_PRICE_PER_MILLION,
                output_price_per_million=self._settings.FURNITURE_QUERY_TERMS_OUTPUT_PRICE_PER_MILLION,
            )
            return QueryTermsBatchResult(
                results_by_crop=normalized,
                raw=parsed,
                usage=usage,
                cost_usd=cost_usd,
                cost_source=cost_source,
                provider="gpt",
                model=model,
            )

        return None

    async def _request_llm(
        self,
        *,
        model: str,
        metadata_json: str,
        crops: list[QueryTermsCropInput],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        url = "https://api.openai.com/v1/responses"
        headers = {
            "Authorization": f"Bearer {self._settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=self._settings.FURNITURE_QUERY_TERMS_TIMEOUT)
        attempts = 2

        for attempt in range(1, attempts + 1):
            user_content: list[dict[str, Any]] = [
                {
                    "type": "input_text",
                    "text": f"metadata_json:\n{metadata_json}",
                },
            ]
            for crop in crops:
                user_content.append(
                    {
                        "type": "input_text",
                        "text": (
                            f"CROP crop_id={crop.crop_id} "
                            f"vision_label={crop.vision_label}"
                        ),
                    }
                )
                user_content.append(
                    _image_part(
                        crop.image_bytes,
                        detail=self._settings.FURNITURE_QUERY_TERMS_IMAGE_DETAIL,
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
                "max_output_tokens": self._settings.FURNITURE_QUERY_TERMS_MAX_OUTPUT_TOKENS,
                "text": {
                    "format": _query_terms_schema_payload(),
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
                                f"OpenAI query_terms error {response.status}: {error_text}"
                            )
                        raw = await response.json()
            except Exception as exc:
                if attempt >= attempts:
                    self._logger.warning(
                        "Furniture query terms failed model=%s: %s",
                        model,
                        exc,
                    )
                    return None, None
                await asyncio.sleep(0.6)
                continue

            text = _extract_openai_text(raw)
            parsed = _parse_json_or_none(text)
            if isinstance(parsed, dict):
                usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else None
                return parsed, usage

            if attempt >= attempts:
                self._logger.warning(
                    "Furniture query terms invalid JSON model=%s chars=%s",
                    model,
                    len(text or ""),
                )
                return None, None
        return None, None


def _query_terms_schema_payload() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "furniture_query_terms_batch",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "crop_id": {"type": "string"},
                            "display_name_ru": {"type": "string"},
                            "query_terms": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["crop_id", "display_name_ru", "query_terms"],
                    },
                }
            },
            "required": ["results"],
        },
    }


def _normalize_results(
    payload: dict[str, Any],
    *,
    expected_ids: set[str],
) -> dict[str, QueryTermsCropResult]:
    raw_results = payload.get("results")
    if not isinstance(raw_results, list):
        return {}
    normalized: dict[str, QueryTermsCropResult] = {}
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        crop_id = str(item.get("crop_id") or "").strip()
        if not crop_id or crop_id not in expected_ids:
            continue
        display = str(item.get("display_name_ru") or "").strip()
        if not display:
            display = "Предмет мебели"
        terms = _normalize_terms(item.get("query_terms"))
        normalized[crop_id] = QueryTermsCropResult(
            crop_id=crop_id,
            display_name_ru=display,
            query_terms=terms,
        )
    return normalized


def _normalize_terms(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        term = " ".join(item.strip().split()).lower()
        if not term or term in seen:
            continue
        seen.add(term)
        normalized.append(term)
        if len(normalized) >= 6:
            break
    return tuple(normalized)


def _build_model_candidates(primary: str, fallback: str | None) -> list[str]:
    models: list[str] = []
    for raw in (primary, fallback or ""):
        model = str(raw or "").strip()
        if not model:
            continue
        if model not in models:
            models.append(model)
    return models


def _image_part(image_bytes: bytes, *, detail: str = "low") -> dict[str, Any]:
    mime = "image/png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    return {
        "type": "input_image",
        "image_url": f"data:{mime};base64,{encoded}",
        "detail": detail,
    }


def _resolve_verbosity_for_model(*, model: str, requested: str) -> str:
    value = str(requested or "medium").strip().lower()
    if value not in _ALLOWED_VERBOSITY_VALUES:
        value = "medium"
    if model.startswith("gpt-4.1") and value == "low":
        return "medium"
    return value


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


def _compute_cost(
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
