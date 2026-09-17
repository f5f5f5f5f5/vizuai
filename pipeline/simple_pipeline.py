"""Simple GPT image pipeline (planner -> render A/B -> AB ranker -> pick best)."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from threading import Lock
from typing import Any

import aiohttp
from PIL import Image, ImageFile, ImageFilter, ImageOps

from config import Settings
from services.decor8 import Decor8Service, extract_decor8_image_urls


SUPPORTED_SIZES = [(1024, 1024), (1024, 1536), (1536, 1024)]
PLANNER_METHOD_IDS = [
    "trash_cleanup",
    "floors_finish_update",
    "walls_finish_update",
    "ceiling_finish_update",
    "lighting_improve",
    "remove_furniture",
    "rearrangement",
    "kitchen_setup",
    "furnishing_general",
    "materials_change",
]
PLANNER_BLOCK_REASON_SAFE = "SAFE"
PLANNER_BLOCK_REASONS = {
    PLANNER_BLOCK_REASON_SAFE,
    "NOT_INTERIOR",
    "LOW_QUALITY",
    "SENSITIVE_CONTENT",
    "DISALLOWED_REQUEST",
}
PLANNER_BLOCK_REASONS_FORBIDDEN = {
    "NOT_INTERIOR",
    "LOW_QUALITY",
    "SENSITIVE_CONTENT",
    "DISALLOWED_REQUEST",
}
DECOR8_FALLBACK_ROOM_TYPE = "livingroom"
DECOR8_FALLBACK_DESIGN_STYLE = "japandi"
_TRUNCATED_IMAGE_LOAD_LOCK = Lock()


@dataclass
class PlannerResult:
    block_reason: str
    methods: list[str]
    room_type: str
    target_style: str
    must_not_change: list[str]
    planner_compiled_prompt: str
    extra_notes: str


@dataclass
class ValidationResult:
    request_ok: bool
    geometry_ok: bool
    function_ok: bool
    scores: dict[str, int]
    notes: str


@dataclass
class SimplePipelineResult:
    best_bytes: bytes
    debug: dict[str, Any]
    prepared_png: bytes
    render_bytes: bytes
    rerender_bytes: bytes | None

    @property
    def fix_bytes(self) -> bytes | None:
        """Backward-compatible alias for legacy callers."""
        return self.rerender_bytes


@dataclass
class ImageCallResult:
    image_bytes: bytes
    provider: str
    cost_usd: float | None = None
    cost_source: str | None = None
    usage: dict[str, Any] | None = None
    request_meta: dict[str, Any] | None = None


@dataclass
class ImageBatchCallResult:
    images: list[bytes]
    usage: dict[str, Any] | None = None
    cost_usd: float | None = None
    cost_source: str | None = None
    request_meta: dict[str, Any] | None = None


@dataclass
class ImagePairCallResult:
    candidate_a: ImageCallResult
    candidate_b: ImageCallResult
    usage: dict[str, Any] | None = None
    cost_usd: float | None = None
    cost_source: str | None = None
    request_meta: dict[str, Any] | None = None


class SimplePipelineError(RuntimeError):
    def __init__(self, message: str, debug: dict[str, Any], stage: str) -> None:
        super().__init__(message)
        self.debug = debug
        self.stage = stage


class PlannerBlockedError(SimplePipelineError):
    def __init__(
        self,
        user_message: str,
        debug: dict[str, Any],
        stage: str,
        block_reason: str,
    ) -> None:
        super().__init__(user_message, debug, stage)
        self.user_message = user_message
        self.block_reason = block_reason


class RenderFallbackError(RuntimeError):
    def __init__(self, openai_error: Exception, fallback_error: Exception) -> None:
        self.openai_error = openai_error
        self.fallback_error = fallback_error
        super().__init__(
            f"render_fallback_failed openai={_exc_debug_text(openai_error)} "
            f"fallback={_exc_debug_text(fallback_error)}"
        )


class SimplePipelineRunner:
    def __init__(self, settings: Settings, logger) -> None:
        self._settings = settings
        self._logger = logger
        self._decor8 = Decor8Service(settings)
        self._planner_prompt_path = Path(settings.SIMPLE_PLANNER_PROMPT_PATH)
        self._planner_style_ref_prompt_path = Path(settings.SIMPLE_PLANNER_STYLE_REF_PROMPT_PATH)
        self._render_prompt_path = Path(settings.SIMPLE_RENDER_PROMPT_PATH)
        self._render_style_ref_prompt_path = Path(settings.SIMPLE_RENDER_STYLE_REF_PROMPT_PATH)
        self._ranker_prompt_path = Path(settings.SIMPLE_RANKER_PROMPT_PATH)
        self._ranker_style_ref_prompt_path = Path(settings.SIMPLE_RANKER_STYLE_REF_PROMPT_PATH)

    async def run(
        self,
        image_bytes: bytes,
        user_request: str,
        job_id: str | None = None,
        style_reference_bytes: bytes | None = None,
        input_image_url: str | None = None,
        style_reference_image_url: str | None = None,
    ) -> SimplePipelineResult:
        debug: dict[str, Any] = {}
        t0 = asyncio.get_running_loop().time()
        timings_s: dict[str, float] = {}
        style_reference_requested = bool(style_reference_bytes)
        if self._logger:
            self._logger.info("simple_pipeline job=%s start", job_id)
            self._logger.info(
                "simple_pipeline job=%s input_prepare_start elapsed=%.2fs",
                job_id,
                asyncio.get_running_loop().time() - t0,
            )

        prepared_png, target_size, prep_meta = _prepare_input_image(image_bytes)
        debug["input_prepared"] = prep_meta
        timings_s["prep"] = round(float(prep_meta.get("total_ms", 0.0)) / 1000.0, 3)
        style_reference_png: bytes | None = None
        style_reference_meta: dict[str, Any] | None = None
        style_reference_status: str | None = None
        style_ref_source = "telegram_user_photo" if style_reference_requested else "none"
        if style_reference_bytes:
            style_ref_t0 = asyncio.get_running_loop().time()
            try:
                style_reference_png, style_reference_meta = _prepare_style_reference_image(
                    style_reference_bytes,
                    target_size,
                )
                timings_s["style_ref_prep"] = round(
                    asyncio.get_running_loop().time() - style_ref_t0,
                    3,
                )
                style_reference_status = "applied"
            except Exception as exc:
                debug["style_reference_error"] = _exc_debug_text(exc)
                debug["style_reference_notice_key"] = "style_ref_not_applied"
                style_reference_status = "fallback_error"
                if self._logger:
                    self._logger.warning(
                        "simple_pipeline job=%s style_reference_prepare_failed error=%s",
                        job_id,
                        _exc_debug_text(exc),
                    )
        if style_reference_status is None and style_reference_requested:
            style_reference_status = "fallback_unknown"
        if style_reference_status is None:
            style_reference_status = "not_requested"
        debug["style_reference_requested"] = style_reference_requested
        debug["style_reference_enabled"] = bool(style_reference_png)
        debug["style_ref_used"] = bool(style_reference_png)
        debug["style_ref_source"] = style_ref_source
        debug["style_reference_status"] = style_reference_status
        if style_reference_meta:
            debug["style_reference_prepared"] = style_reference_meta
        if self._logger:
            try:
                prep_meta_json = json.dumps(prep_meta, ensure_ascii=False, sort_keys=True)
            except Exception:
                prep_meta_json = str(prep_meta)
            self._logger.info(
                "simple_pipeline job=%s input_prepared size=%s meta=%s elapsed=%.2fs",
                job_id,
                target_size,
                prep_meta_json,
                asyncio.get_running_loop().time() - t0,
            )
            if style_reference_meta:
                try:
                    style_meta_json = json.dumps(style_reference_meta, ensure_ascii=False, sort_keys=True)
                except Exception:
                    style_meta_json = str(style_reference_meta)
                self._logger.info(
                    "simple_pipeline job=%s style_reference_prepared status=%s size=%s meta=%s elapsed=%.2fs",
                    job_id,
                    style_reference_status,
                    target_size,
                    style_meta_json,
                    asyncio.get_running_loop().time() - t0,
                )

        planner_prompt_path = (
            self._planner_style_ref_prompt_path if style_reference_png else self._planner_prompt_path
        )
        planner_instruction = _load_text(planner_prompt_path)
        planner_temperature = (
            self._settings.OPENAI_PLANNER_TEMPERATURE
            if self._settings.OPENAI_TEXT_SEND_TEMPERATURE
            else None
        )
        planner_t0 = asyncio.get_running_loop().time()
        if self._logger:
            self._logger.info(
                "simple_pipeline job=%s planner_start elapsed=%.2fs",
                job_id,
                asyncio.get_running_loop().time() - t0,
            )
        (
            planner_raw,
            planner,
            planner_provider,
            planner_usage,
            planner_cost,
            planner_attempts,
            planner_error,
            planner_parse_mode,
            planner_text_fallback_used,
            planner_schema,
        ) = await _planner_with_json_retry(
            settings=self._settings,
            instruction=planner_instruction,
            user_text=user_request,
            images=[image_bytes, style_reference_png]
            if style_reference_png
            else [image_bytes],
            max_output_tokens=self._settings.OPENAI_PLANNER_MAX_OUTPUT_TOKENS,
            temperature=planner_temperature,
            reasoning_effort=self._settings.OPENAI_PLANNER_REASONING_EFFORT,
            text_verbosity=self._settings.OPENAI_TEXT_VERBOSITY,
            store=self._settings.OPENAI_TEXT_STORE,
            gemini_temperature=0.2,
            logger=self._logger,
            job_id=job_id,
        )
        debug["planner_provider"] = planner_provider
        debug["planner_raw"] = planner_raw
        debug["planner_usage"] = planner_usage
        debug["planner_cost_usd"] = planner_cost
        debug["planner_attempts"] = planner_attempts
        debug["planner_parse_mode"] = planner_parse_mode
        debug["planner_text_fallback_used"] = planner_text_fallback_used
        debug["planner_schema"] = planner_schema
        timings_s["planner"] = round(asyncio.get_running_loop().time() - planner_t0, 3)
        if self._logger:
            self._logger.info(
                "simple_pipeline job=%s planner_done provider=%s attempts=%d tokens=%s cost_usd=%s style_ref=%s elapsed=%.2fs",
                job_id,
                planner_provider,
                len(planner_attempts),
                planner_usage,
                planner_cost,
                bool(style_reference_png),
                asyncio.get_running_loop().time() - t0,
            )
        if planner is None:
            raise SimplePipelineError(
                f"Planner returned invalid JSON: {planner_error or 'unknown planner parse error'}",
                debug,
                "planner_parse",
            )
        debug["planner"] = planner.__dict__
        block_reason = _normalize_block_reason(planner.block_reason)
        debug["planner_block_reason"] = block_reason
        if block_reason in PLANNER_BLOCK_REASONS_FORBIDDEN:
            debug["planner_blocked"] = True
            block_message = _planner_block_message(block_reason, planner.extra_notes)
            debug["planner_block_message"] = block_message
            timings_s["total"] = round(asyncio.get_running_loop().time() - t0, 3)
            debug["timings_s"] = timings_s
            raise PlannerBlockedError(
                user_message=block_message,
                debug=debug,
                stage="planner_blocked",
                block_reason=block_reason,
            )
        debug["planner_blocked"] = False

        render_template_default = _load_text(self._render_prompt_path)
        render_template_style_ref = _load_text(self._render_style_ref_prompt_path)
        debug["render_prompt_path"] = str(
            self._render_style_ref_prompt_path if style_reference_png else self._render_prompt_path
        )
        if self._logger:
            self._logger.info(
                "simple_pipeline job=%s render_ab_start size=%s style_ref=%s elapsed=%.2fs",
                job_id,
                target_size,
                bool(style_reference_png),
                asyncio.get_running_loop().time() - t0,
            )

        def _record_candidate_success(
            *,
            candidate_key: str,
            legacy_key: str,
            call: ImageCallResult,
            used_style_ref: bool,
            prompt_used: str,
            render_t0: float,
            first_error: Exception | None = None,
            emit_log: bool = True,
        ) -> None:
            debug[f"{candidate_key}_provider"] = call.provider
            debug[f"{candidate_key}_usage"] = call.usage
            debug[f"{candidate_key}_cost_usd"] = call.cost_usd
            debug[f"{candidate_key}_cost_source"] = call.cost_source
            debug[f"{candidate_key}_style_ref_used"] = used_style_ref
            if call.request_meta is not None:
                debug[f"{candidate_key}_request_meta"] = call.request_meta
            debug[f"{legacy_key}_provider"] = call.provider
            debug[f"{legacy_key}_usage"] = call.usage
            debug[f"{legacy_key}_cost_usd"] = call.cost_usd
            debug[f"{legacy_key}_cost_source"] = call.cost_source
            debug[f"{legacy_key}_style_ref_used"] = used_style_ref
            if call.request_meta is not None:
                debug[f"{legacy_key}_request_meta"] = call.request_meta
            if first_error is not None and not used_style_ref:
                debug[f"{candidate_key}_style_ref_drop_reason"] = _exc_debug_text(first_error)
                debug[f"{legacy_key}_style_ref_drop_reason"] = _exc_debug_text(first_error)
            if call.provider == "gpt" and call.cost_usd is None:
                debug[f"{candidate_key}_cost_missing"] = True
                debug[f"{legacy_key}_cost_missing"] = True
                if self._logger:
                    self._logger.warning(
                        "simple_pipeline job=%s %s_cost_missing usage_keys=%s prices_set=%s/%s price_table=%s",
                        job_id,
                        candidate_key,
                        sorted(list((call.usage or {}).keys())),
                        self._settings.OPENAI_IMAGE_INPUT_PRICE_PER_MILLION is not None,
                        self._settings.OPENAI_IMAGE_OUTPUT_PRICE_PER_MILLION is not None,
                        bool(self._settings.OPENAI_IMAGE_PRICE_TABLE_JSON),
                    )
            timings_s[candidate_key] = round(asyncio.get_running_loop().time() - render_t0, 3)
            debug[f"{candidate_key}_prompt_chars"] = len(prompt_used)
            debug[f"{legacy_key}_prompt_chars"] = len(prompt_used)
            debug[f"{candidate_key}_prompt_variant"] = "style_ref" if used_style_ref else "default"
            debug[f"{legacy_key}_prompt_variant"] = "style_ref" if used_style_ref else "default"
            if self._logger and emit_log:
                self._logger.info(
                    "simple_pipeline job=%s %s_done provider=%s size=%s prompt_chars=%d cost_usd=%s cost_source=%s elapsed=%.2fs",
                    job_id,
                    candidate_key,
                    call.provider,
                    target_size,
                    len(prompt_used),
                    call.cost_usd,
                    call.cost_source,
                    asyncio.get_running_loop().time() - t0,
                )

        candidate_a_call: ImageCallResult | None = None
        candidate_b_call: ImageCallResult | None = None
        batch_render_t0 = asyncio.get_running_loop().time()
        batch_style_ref_used = bool(style_reference_png)
        batch_prompt_used = _assemble_render_prompt(
            render_template_style_ref if batch_style_ref_used else render_template_default,
            planner,
        )
        decor8_prompt_used = batch_prompt_used
        batch_pair: ImagePairCallResult | None = None
        try:
            batch_pair = await _render_pair_primary_openai_with_retry(
                settings=self._settings,
                image_bytes=prepared_png,
                aux_image_bytes=style_reference_png if batch_style_ref_used else None,
                prompt=batch_prompt_used,
                size=target_size,
                logger=self._logger,
                job_id=job_id,
            )
        except Exception as exc:
            debug["render_batch_error"] = _exc_debug_text(exc)
            debug["render_batch_openai_error"] = _exc_debug_text(exc)
            if self._logger:
                self._logger.warning(
                    "simple_pipeline job=%s render_batch_primary_failed fallback=decor8 error=%s",
                    job_id,
                    _exc_debug_text(exc),
                )
            try:
                fallback_style_ref_used = bool(style_reference_image_url)
                try:
                    batch_pair = await _render_pair_decor8(
                        settings=self._settings,
                        decor8=self._decor8,
                        input_image_url=input_image_url,
                        room_type=DECOR8_FALLBACK_ROOM_TYPE,
                        design_style=DECOR8_FALLBACK_DESIGN_STYLE,
                        prompt=decor8_prompt_used,
                        design_style_image_url=style_reference_image_url,
                        logger=self._logger,
                        job_id=job_id,
                    )
                except Exception as fallback_exc:
                    debug["render_batch_fallback_error"] = _exc_debug_text(fallback_exc)
                    if not style_reference_image_url:
                        raise
                    debug["render_batch_fallback_retry_without_style_ref"] = True
                    debug["render_batch_fallback_with_style_ref_error"] = _exc_debug_text(
                        fallback_exc
                    )
                    debug["render_batch_style_ref_dropped"] = True
                    debug["render_batch_style_ref_drop_reason"] = "decor8_retry_without_style_ref"
                    if self._logger:
                        self._logger.warning(
                            "simple_pipeline job=%s render_batch_decor8_retry_without_style_ref error=%s",
                            job_id,
                            _exc_debug_text(fallback_exc),
                        )
                    batch_pair = await _render_pair_decor8(
                        settings=self._settings,
                        decor8=self._decor8,
                        input_image_url=input_image_url,
                        room_type=DECOR8_FALLBACK_ROOM_TYPE,
                        design_style=DECOR8_FALLBACK_DESIGN_STYLE,
                        prompt=decor8_prompt_used,
                        design_style_image_url=None,
                        logger=self._logger,
                        job_id=job_id,
                    )
                    fallback_style_ref_used = False
                if batch_style_ref_used and not fallback_style_ref_used:
                    debug["render_batch_style_ref_dropped"] = True
                    debug.setdefault(
                        "render_batch_style_ref_drop_reason",
                        "decor8_fallback_without_style_ref",
                    )
                batch_style_ref_used = fallback_style_ref_used
                if fallback_style_ref_used:
                    style_reference_status = "applied"
            except Exception as fallback_exc:
                debug["render_batch_fallback_error"] = _exc_debug_text(fallback_exc)
                raise SimplePipelineError(
                    "Both render candidates failed",
                    debug,
                    "render_ab",
                ) from RenderFallbackError(exc, fallback_exc)
        if batch_pair is not None:
            debug["render_batch_primary_used"] = batch_pair.candidate_a.provider == "gpt"
            debug["render_batch_provider"] = batch_pair.candidate_a.provider
            if batch_pair.candidate_a.provider != "gpt":
                debug["render_batch_fallback_provider"] = batch_pair.candidate_a.provider
            debug["render_batch_usage"] = batch_pair.usage
            debug["render_batch_cost_usd"] = batch_pair.cost_usd
            debug["render_batch_cost_source"] = batch_pair.cost_source
            debug["render_batch_request_meta"] = batch_pair.request_meta
            effective_batch_prompt = (
                batch_prompt_used if batch_pair.candidate_a.provider == "gpt" else decor8_prompt_used
            )
            debug["render_batch_prompt_chars"] = len(effective_batch_prompt)
            debug["render_batch_prompt_variant"] = (
                "style_ref"
                if batch_pair.candidate_a.provider == "gpt" and batch_style_ref_used
                else "default"
            )
            candidate_a_call = batch_pair.candidate_a
            candidate_b_call = batch_pair.candidate_b
            _record_candidate_success(
                candidate_key="candidate_a",
                legacy_key="render",
                call=candidate_a_call,
                used_style_ref=batch_style_ref_used,
                prompt_used=effective_batch_prompt,
                render_t0=batch_render_t0,
                emit_log=False,
            )
            _record_candidate_success(
                candidate_key="candidate_b",
                legacy_key="rerender",
                call=candidate_b_call,
                used_style_ref=batch_style_ref_used,
                prompt_used=effective_batch_prompt,
                render_t0=batch_render_t0,
                emit_log=False,
            )
            if self._logger:
                request_meta = batch_pair.request_meta or {}
                primary_meta = request_meta.get("primary") or {}
                aux_meta = request_meta.get("aux") or {}
                self._logger.info(
                    "simple_pipeline job=%s render_batch_done provider=%s outputs=%d size=%s prompt_chars=%d total_cost_usd=%s cost_source=%s input_format=%s input_bytes=%s aux_format=%s aux_bytes=%s elapsed=%.2fs",
                    job_id,
                    batch_pair.candidate_a.provider,
                    2,
                    target_size,
                    len(batch_prompt_used),
                    batch_pair.cost_usd,
                    batch_pair.cost_source,
                    primary_meta.get("format"),
                    primary_meta.get("encoded_bytes"),
                    aux_meta.get("format"),
                    aux_meta.get("encoded_bytes"),
                    asyncio.get_running_loop().time() - t0,
                )
        candidate_a_bytes = candidate_a_call.image_bytes if candidate_a_call else None
        candidate_b_bytes = candidate_b_call.image_bytes if candidate_b_call else None
        candidate_a_style_ref_used = bool(debug.get("candidate_a_style_ref_used"))
        candidate_b_style_ref_used = bool(debug.get("candidate_b_style_ref_used"))
        style_reference_used_any = candidate_a_style_ref_used or candidate_b_style_ref_used
        if candidate_a_bytes is None and candidate_b_bytes is None:
            raise SimplePipelineError(
                "Both render candidates failed",
                debug,
                "render_ab",
            )

        ranker_best_label = "A"
        ranker_result: dict[str, Any] | None = None

        if candidate_a_bytes is not None and candidate_b_bytes is not None:
            ranker_prompt_path = (
                self._ranker_style_ref_prompt_path
                if style_reference_png and style_reference_used_any
                else self._ranker_prompt_path
            )
            ranker_instruction = _load_system_prompt(ranker_prompt_path)
            debug["ranker_prompt_path"] = str(ranker_prompt_path)
            ranker_temperature = (
                self._settings.OPENAI_RANKER_TEMPERATURE
                if self._settings.OPENAI_TEXT_SEND_TEMPERATURE
                else None
            )
            ranker_t0 = asyncio.get_running_loop().time()
            ranker_raw = ""
            ranker_parsed: dict[str, Any] | None = None
            ranker_provider = "unknown"
            ranker_usage: dict | None = None
            ranker_cost: float | None = None
            ranker_attempts: list[dict[str, Any]] = []
            ranker_error: str | None = None
            ranker_parse_mode: str | None = None
            ranker_schema: dict[str, Any] = {
                "requested": True,
                "applied": False,
                "fallback_reason": "ranker_exception",
            }
            if self._logger:
                self._logger.info(
                    "simple_pipeline job=%s ranker_start elapsed=%.2fs",
                    job_id,
                    asyncio.get_running_loop().time() - t0,
                )
            try:
                (
                    ranker_raw,
                    ranker_parsed,
                    ranker_provider,
                    ranker_usage,
                    ranker_cost,
                    ranker_attempts,
                    ranker_error,
                    ranker_parse_mode,
                    ranker_schema,
                ) = await _ranker_with_json_retry(
                    settings=self._settings,
                    instruction=ranker_instruction,
                    user_text=_build_ranker_user_text(
                        user_request=user_request,
                        must_not_change=planner.must_not_change,
                        style_reference_enabled=style_reference_used_any,
                    ),
                    images=[prepared_png, candidate_a_bytes, candidate_b_bytes]
                    + ([style_reference_png] if style_reference_png and style_reference_used_any else []),
                    max_output_tokens=self._settings.OPENAI_RANKER_MAX_OUTPUT_TOKENS,
                    temperature=ranker_temperature,
                    reasoning_effort=self._settings.OPENAI_RANKER_REASONING_EFFORT,
                    text_verbosity=self._settings.OPENAI_TEXT_VERBOSITY,
                    store=self._settings.OPENAI_TEXT_STORE,
                    gemini_temperature=0.0,
                    logger=self._logger,
                    job_id=job_id,
                )
            except Exception as exc:
                ranker_error = f"{type(exc).__name__}: {exc}"
                debug["ranker_fallback_reason"] = "ranker_exception_select_a"
                debug["ranker_error"] = ranker_error
                if self._logger:
                    self._logger.warning(
                        "simple_pipeline job=%s ranker_failed_select_a elapsed=%.2fs error=%s",
                        job_id,
                        asyncio.get_running_loop().time() - t0,
                        ranker_error,
                    )
            debug["ranker_provider"] = ranker_provider
            debug["ranker_ab_raw"] = ranker_raw
            debug["ranker_usage"] = ranker_usage
            debug["ranker_cost_usd"] = ranker_cost
            debug["ranker_attempts"] = ranker_attempts
            debug["ranker_schema"] = ranker_schema
            debug["ranker_parse_mode"] = ranker_parse_mode
            timings_s["ranker"] = round(asyncio.get_running_loop().time() - ranker_t0, 3)
            if self._logger and ranker_error is None:
                self._logger.info(
                    "simple_pipeline job=%s ranker_done provider=%s attempts=%d tokens=%s cost_usd=%s elapsed=%.2fs",
                    job_id,
                    ranker_provider,
                    len(ranker_attempts),
                    ranker_usage,
                    ranker_cost,
                    asyncio.get_running_loop().time() - t0,
                )

            if ranker_parsed is None:
                debug["ranker_fallback_reason"] = debug.get("ranker_fallback_reason") or "invalid_json_after_retry"
                debug["ranker_error"] = ranker_error
                ranker_best_label = "A"
            else:
                ranker_result = _normalize_ranker_payload(ranker_parsed)
                debug["ranker_ab"] = ranker_result
                if not isinstance(ranker_result.get("A"), dict) or not isinstance(ranker_result.get("B"), dict):
                    debug["ranker_fallback_reason"] = "missing_candidates_select_a"
                    ranker_best_label = "A"
                    ranker_result = None
                else:
                    best_raw = str(ranker_result.get("best", "")).strip().upper()
                    if best_raw == "B":
                        ranker_best_label = "B"
                    elif best_raw == "TIE":
                        debug["ranker_fallback_reason"] = "tie_select_a"
                        ranker_best_label = "A"
                    elif best_raw != "A":
                        debug["ranker_fallback_reason"] = "unknown_best_select_a"
                        ranker_best_label = "A"
        elif candidate_b_bytes is not None:
            ranker_best_label = "B"
            debug["ranker_skipped_reason"] = "candidate_a_missing"
        else:
            ranker_best_label = "A"
            debug["ranker_skipped_reason"] = "candidate_b_missing"

        best_bytes: bytes
        if ranker_best_label == "B" and candidate_b_bytes is not None:
            best_bytes = candidate_b_bytes
            best_label = "B"
        else:
            best_bytes = candidate_a_bytes or candidate_b_bytes
            if best_bytes is None:
                raise SimplePipelineError("No successful render candidate", debug, "render_ab")
            best_label = "A" if candidate_a_bytes is not None else "B"
        best_style_ref_used = (
            candidate_a_style_ref_used if best_label == "A" else candidate_b_style_ref_used
        )
        if style_reference_requested and not best_style_ref_used:
            debug["style_reference_notice_key"] = "style_ref_not_applied"
            if style_reference_status == "applied":
                style_reference_status = "fallback_error"
        debug["style_reference_enabled"] = bool(best_style_ref_used)
        debug["style_ref_used"] = bool(best_style_ref_used)
        debug["style_ref_source"] = style_ref_source
        debug["style_reference_status"] = style_reference_status

        if ranker_result:
            a_validation = _validation_from_ranker_candidate(
                ranker_result.get("A"),
                fallback_notes="ranker_A",
            )
            b_validation = _validation_from_ranker_candidate(
                ranker_result.get("B"),
                fallback_notes="ranker_B",
            )
            debug["render_validation"] = a_validation.__dict__
            debug["rerender_validation"] = b_validation.__dict__
            debug["render_score"] = _overall_score(a_validation.scores)
            debug["rerender_score"] = _overall_score(b_validation.scores)
            debug["render_ok"] = (
                a_validation.request_ok and a_validation.geometry_ok and a_validation.function_ok
            )
            debug["rerender_ok"] = (
                b_validation.request_ok and b_validation.geometry_ok and b_validation.function_ok
            )
            debug["best_ok"] = bool(debug["render_ok"]) if best_label == "A" else bool(debug["rerender_ok"])
        else:
            debug["best_ok"] = best_bytes is not None

        debug["best_label"] = best_label
        image_cost_total = _sum_cost_values(
            debug.get("candidate_a_cost_usd"),
            debug.get("candidate_b_cost_usd"),
        )
        debug["image_cost_total_usd"] = image_cost_total
        debug["image_cost_sources"] = [
            source
            for source in [debug.get("candidate_a_cost_source"), debug.get("candidate_b_cost_source")]
            if isinstance(source, str) and source.strip()
        ]
        debug["image_pricing_config"] = {
            "input_per_million_set": self._settings.OPENAI_IMAGE_INPUT_PRICE_PER_MILLION is not None,
            "output_per_million_set": self._settings.OPENAI_IMAGE_OUTPUT_PRICE_PER_MILLION is not None,
            "price_table_present": bool(self._settings.OPENAI_IMAGE_PRICE_TABLE_JSON),
        }
        degraded_reasons = _compute_degraded_reasons(
            debug,
            style_reference_requested=style_reference_requested,
        )
        debug["degraded"] = bool(degraded_reasons)
        debug["degraded_reasons"] = degraded_reasons
        if self._logger:
            self._logger.info(
                "simple_pipeline job=%s done best=%s degraded=%s degraded_reasons=%s style_ref_requested=%s style_ref_used=%s style_ref_source=%s style_ref_status=%s elapsed=%.2fs",
                job_id,
                debug.get("best_label"),
                bool(debug.get("degraded")),
                debug.get("degraded_reasons"),
                style_reference_requested,
                bool(debug.get("style_ref_used")),
                debug.get("style_ref_source"),
                style_reference_status,
                asyncio.get_running_loop().time() - t0,
            )
        timings_s["total"] = round(asyncio.get_running_loop().time() - t0, 3)
        debug["timings_s"] = timings_s

        return SimplePipelineResult(
            best_bytes=best_bytes,
            debug=debug,
            prepared_png=prepared_png,
            render_bytes=candidate_a_bytes or best_bytes,
            rerender_bytes=candidate_b_bytes,
        )


def _load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _load_system_prompt(path: Path) -> str:
    text = _load_text(path)
    if text.upper().startswith("SYSTEM_PROMPT"):
        lines = text.splitlines()
        return "\n".join(lines[1:]).strip()
    return text


def _decode_image_bytes(
    image_bytes: bytes,
    *,
    mode: str = "RGB",
) -> tuple[Image.Image, dict[str, bool]]:
    try:
        image = Image.open(BytesIO(image_bytes))
        orientation_before = image.getexif().get(274) if hasattr(image, "getexif") else None
        image = ImageOps.exif_transpose(image).convert(mode)
        return image, {
            "truncated_recovery_applied": False,
            "exif_transpose_applied": bool(orientation_before and orientation_before != 1),
        }
    except OSError as exc:
        if "truncated" not in str(exc).lower():
            raise

    with _TRUNCATED_IMAGE_LOAD_LOCK:
        previous = ImageFile.LOAD_TRUNCATED_IMAGES
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            image = Image.open(BytesIO(image_bytes))
            orientation_before = image.getexif().get(274) if hasattr(image, "getexif") else None
            image = ImageOps.exif_transpose(image).convert(mode)
            return image, {
                "truncated_recovery_applied": True,
                "exif_transpose_applied": bool(orientation_before and orientation_before != 1),
            }
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = previous


def _prepare_input_image(image_bytes: bytes) -> tuple[bytes, str, dict[str, Any]]:
    t0 = time.perf_counter()
    image, decode_flags = _decode_image_bytes(image_bytes)
    decode_ms = (time.perf_counter() - t0) * 1000.0
    choose_t0 = time.perf_counter()
    target = _choose_target_size(image.size)
    choose_size_ms = (time.perf_counter() - choose_t0) * 1000.0
    fit_t0 = time.perf_counter()
    prepared, fit_detail = _fit_image(
        image,
        target,
        mode="pad",
        pad_style="blur",
        collect_timing=True,
    )
    fit_ms = (time.perf_counter() - fit_t0) * 1000.0
    encode_t0 = time.perf_counter()
    prepared_png, encode_detail = _to_png_bytes(
        prepared,
        compress_level=1,
        optimize=False,
        collect_timing=True,
    )
    encode_ms = (time.perf_counter() - encode_t0) * 1000.0
    total_ms = (time.perf_counter() - t0) * 1000.0
    meta = {
        "original_size": list(image.size),
        "target_size": list(target),
        "target_size_label": f"{target[0]}x{target[1]}",
        "fit_mode": "pad",
        "pad_style": "blur",
        "decode_truncated_recovery_applied": decode_flags["truncated_recovery_applied"],
        "decode_exif_transpose_applied": decode_flags["exif_transpose_applied"],
        "decode_ms": round(decode_ms, 2),
        "choose_size_ms": round(choose_size_ms, 2),
        "fit_ms": round(fit_ms, 2),
        "encode_ms": round(encode_ms, 2),
        "encode_format": "png",
        "encode_profile": "png_fast",
        "encoded_bytes": len(prepared_png),
        "total_ms": round(total_ms, 2),
    }
    for key, value in fit_detail.items():
        meta[f"fit_{key}"] = round(float(value), 2)
    for key, value in encode_detail.items():
        meta[f"encode_{key}"] = round(float(value), 2)
    return prepared_png, meta["target_size_label"], meta


def _parse_target_size_label(size_label: str) -> tuple[int, int]:
    match = str(size_label or "").lower().strip().split("x", 1)
    if len(match) != 2:
        return SUPPORTED_SIZES[0]
    try:
        width = int(match[0])
        height = int(match[1])
    except Exception:
        return SUPPORTED_SIZES[0]
    if width <= 0 or height <= 0:
        return SUPPORTED_SIZES[0]
    return width, height


def _prepare_style_reference_image(
    image_bytes: bytes,
    target_size_label: str,
) -> tuple[bytes, dict[str, Any]]:
    t0 = time.perf_counter()
    image, decode_flags = _decode_image_bytes(image_bytes)
    decode_ms = (time.perf_counter() - t0) * 1000.0
    target = _parse_target_size_label(target_size_label)
    fit_t0 = time.perf_counter()
    target_w, target_h = target
    scale = min(1.0, target_w / image.width, target_h / image.height)
    resize_ms = 0.0
    if scale < 1.0:
        new_w = max(1, int(image.width * scale))
        new_h = max(1, int(image.height * scale))
        resize_t0 = time.perf_counter()
        prepared = image.resize((new_w, new_h), resample=Image.LANCZOS)
        resize_ms = (time.perf_counter() - resize_t0) * 1000.0
    else:
        prepared = image.copy()
    fit_ms = (time.perf_counter() - fit_t0) * 1000.0
    encode_t0 = time.perf_counter()
    png_bytes, encode_detail = _to_png_bytes(
        prepared,
        compress_level=1,
        optimize=False,
        collect_timing=True,
    )
    encode_ms = (time.perf_counter() - encode_t0) * 1000.0
    total_ms = (time.perf_counter() - t0) * 1000.0
    meta = {
        "original_size": list(image.size),
        "prepared_size": list(prepared.size),
        "target_size": [target[0], target[1]],
        "target_size_label": f"{target[0]}x{target[1]}",
        "fit_mode": "contain_no_upscale",
        "decode_truncated_recovery_applied": decode_flags["truncated_recovery_applied"],
        "decode_exif_transpose_applied": decode_flags["exif_transpose_applied"],
        "decode_ms": round(decode_ms, 2),
        "fit_ms": round(fit_ms, 2),
        "fit_resize_ms": round(resize_ms, 2),
        "encode_ms": round(encode_ms, 2),
        "encoded_bytes": len(png_bytes),
        "total_ms": round(total_ms, 2),
    }
    for key, value in encode_detail.items():
        meta[f"encode_{key}"] = round(float(value), 2)
    return png_bytes, meta


def _compute_degraded_reasons(
    debug: dict[str, Any],
    *,
    style_reference_requested: bool,
) -> list[str]:
    reasons: list[str] = []

    def _add(reason: str | None) -> None:
        if reason and reason not in reasons:
            reasons.append(reason)

    if debug.get("render_batch_error"):
        _add("render_batch_fallback")
    planner_provider = str(debug.get("planner_provider") or "").strip().lower()
    if planner_provider and planner_provider != "gpt":
        _add("planner_provider_fallback")
    candidate_a_provider = str(debug.get("candidate_a_provider") or "").strip().lower()
    if candidate_a_provider and candidate_a_provider != "gpt":
        _add("candidate_a_provider_fallback")
    candidate_b_provider = str(debug.get("candidate_b_provider") or "").strip().lower()
    if candidate_b_provider and candidate_b_provider != "gpt":
        _add("candidate_b_provider_fallback")
    if debug.get("candidate_a_error"):
        _add("candidate_a_failed")
    if debug.get("candidate_b_error"):
        _add("candidate_b_failed")
    if debug.get("ranker_skipped_reason"):
        _add("ranker_skipped")
    if debug.get("ranker_fallback_reason"):
        _add("ranker_fallback")
    ranker_provider = str(debug.get("ranker_provider") or "").strip().lower()
    if ranker_provider and ranker_provider not in {"", "gpt", "unknown"}:
        _add("ranker_provider_fallback")
    if style_reference_requested and not bool(debug.get("style_ref_used")):
        _add("style_ref_not_applied")
    return reasons


def _choose_target_size(size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    best = None
    best_score = None
    for tw, th in SUPPORTED_SIZES:
        scale = min(tw / width, th / height)
        new_w = int(width * scale)
        new_h = int(height * scale)
        pad_area = (tw * th) - (new_w * new_h)
        score = pad_area
        if best_score is None or score < best_score:
            best_score = score
            best = (tw, th)
    return best or SUPPORTED_SIZES[0]


def _fit_image(
    image: Image.Image,
    target: tuple[int, int],
    mode: str,
    pad_style: str,
    collect_timing: bool = False,
) -> Image.Image | tuple[Image.Image, dict[str, float]]:
    fit_t0 = time.perf_counter()
    timings: dict[str, float] = {}
    target_w, target_h = target
    if mode == "stretch":
        resize_t0 = time.perf_counter()
        result = image.resize((target_w, target_h), resample=Image.LANCZOS)
        timings["resize_ms"] = (time.perf_counter() - resize_t0) * 1000.0
        timings["total_ms"] = (time.perf_counter() - fit_t0) * 1000.0
        return (result, timings) if collect_timing else result
    if mode == "pad":
        scale = min(target_w / image.width, target_h / image.height)
        new_w = max(1, int(image.width * scale))
        new_h = max(1, int(image.height * scale))
        resize_t0 = time.perf_counter()
        resized = image.resize((new_w, new_h), resample=Image.LANCZOS)
        timings["resize_ms"] = (time.perf_counter() - resize_t0) * 1000.0
        if pad_style == "blur":
            bg_resize_t0 = time.perf_counter()
            background = image.resize((target_w, target_h), resample=Image.LANCZOS)
            timings["background_resize_ms"] = (time.perf_counter() - bg_resize_t0) * 1000.0
            blur_t0 = time.perf_counter()
            background = background.filter(ImageFilter.GaussianBlur(radius=12))
            timings["blur_ms"] = (time.perf_counter() - blur_t0) * 1000.0
        else:
            bg_fill_t0 = time.perf_counter()
            background = Image.new("RGB", (target_w, target_h), color=(16, 16, 16))
            timings["background_fill_ms"] = (time.perf_counter() - bg_fill_t0) * 1000.0
        offset = ((target_w - new_w) // 2, (target_h - new_h) // 2)
        paste_t0 = time.perf_counter()
        background.paste(resized, offset)
        timings["paste_ms"] = (time.perf_counter() - paste_t0) * 1000.0
        timings["total_ms"] = (time.perf_counter() - fit_t0) * 1000.0
        return (background, timings) if collect_timing else background
    # crop
    scale = max(target_w / image.width, target_h / image.height)
    new_w = max(1, int(image.width * scale))
    new_h = max(1, int(image.height * scale))
    resize_t0 = time.perf_counter()
    resized = image.resize((new_w, new_h), resample=Image.LANCZOS)
    timings["resize_ms"] = (time.perf_counter() - resize_t0) * 1000.0
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    crop_t0 = time.perf_counter()
    result = resized.crop((left, top, left + target_w, top + target_h))
    timings["crop_ms"] = (time.perf_counter() - crop_t0) * 1000.0
    timings["total_ms"] = (time.perf_counter() - fit_t0) * 1000.0
    return (result, timings) if collect_timing else result


def _to_jpeg_bytes(
    image_input: bytes | Image.Image,
    *,
    quality: int = 88,
    optimize: bool = True,
    collect_timing: bool = False,
) -> bytes | tuple[bytes, dict[str, float]]:
    encode_t0 = time.perf_counter()
    timings: dict[str, float] = {}
    if isinstance(image_input, Image.Image):
        convert_t0 = time.perf_counter()
        image = image_input.convert("RGB")
        timings["convert_ms"] = (time.perf_counter() - convert_t0) * 1000.0
    else:
        convert_t0 = time.perf_counter()
        image, _ = _decode_image_bytes(image_input)
        timings["convert_ms"] = (time.perf_counter() - convert_t0) * 1000.0
    buffer = BytesIO()
    save_t0 = time.perf_counter()
    image.save(
        buffer,
        format="JPEG",
        quality=max(60, min(95, int(quality))),
        optimize=bool(optimize),
    )
    timings["save_ms"] = (time.perf_counter() - save_t0) * 1000.0
    timings["total_ms"] = (time.perf_counter() - encode_t0) * 1000.0
    result = buffer.getvalue()
    return (result, timings) if collect_timing else result


def _prepare_openai_edit_transport(
    image_input: bytes | Image.Image,
    *,
    max_long_edge: int,
    preferred_format: str,
    jpeg_quality: int,
    filename_stem: str,
) -> tuple[bytes, str, str, dict[str, Any]]:
    if isinstance(image_input, Image.Image):
        image = image_input.convert("RGB")
    else:
        image, _ = _decode_image_bytes(image_input)
    original_size = list(image.size)
    resize_applied = False
    max_dimension = max(image.size) if image.size else 0
    if max_long_edge > 0 and max_dimension > max_long_edge:
        scale = max_long_edge / float(max_dimension)
        new_size = (
            max(1, int(round(image.width * scale))),
            max(1, int(round(image.height * scale))),
        )
        image = image.resize(new_size, resample=Image.LANCZOS)
        resize_applied = True
    prepared_size = list(image.size)
    normalized_format = str(preferred_format or "jpeg").strip().lower()
    if normalized_format in {"jpg", "jpeg"}:
        encoded, encode_detail = _to_jpeg_bytes(
            image,
            quality=jpeg_quality,
            optimize=True,
            collect_timing=True,
        )
        meta = {
            "format": "jpeg",
            "content_type": "image/jpeg",
            "filename": f"{filename_stem}.jpg",
        }
    else:
        encoded, encode_detail = _to_png_bytes(
            image,
            compress_level=1,
            optimize=False,
            collect_timing=True,
        )
        meta = {
            "format": "png",
            "content_type": "image/png",
            "filename": f"{filename_stem}.png",
        }
    meta.update(
        {
            "original_size": original_size,
            "prepared_size": prepared_size,
            "max_long_edge": max_long_edge,
            "resize_applied": resize_applied,
            "encoded_bytes": len(encoded),
        }
    )
    for key, value in encode_detail.items():
        meta[f"encode_{key}"] = round(float(value), 2)
    return encoded, meta["filename"], meta["content_type"], meta


def _to_png_bytes(
    image_input: bytes | Image.Image,
    *,
    compress_level: int = 1,
    optimize: bool = False,
    collect_timing: bool = False,
) -> bytes | tuple[bytes, dict[str, float]]:
    encode_t0 = time.perf_counter()
    timings: dict[str, float] = {}
    if isinstance(image_input, bytes) and image_input.startswith(b"\x89PNG\r\n\x1a\n"):
        timings["passthrough_ms"] = (time.perf_counter() - encode_t0) * 1000.0
        timings["total_ms"] = timings["passthrough_ms"]
        return (image_input, timings) if collect_timing else image_input
    if isinstance(image_input, Image.Image):
        convert_t0 = time.perf_counter()
        image = image_input.convert("RGB")
        timings["convert_ms"] = (time.perf_counter() - convert_t0) * 1000.0
    else:
        convert_t0 = time.perf_counter()
        image, _ = _decode_image_bytes(image_input)
        timings["convert_ms"] = (time.perf_counter() - convert_t0) * 1000.0
    buffer = BytesIO()
    save_t0 = time.perf_counter()
    image.save(
        buffer,
        format="PNG",
        compress_level=max(0, min(9, int(compress_level))),
        optimize=bool(optimize),
    )
    timings["save_ms"] = (time.perf_counter() - save_t0) * 1000.0
    timings["total_ms"] = (time.perf_counter() - encode_t0) * 1000.0
    result = buffer.getvalue()
    return (result, timings) if collect_timing else result


def _extract_json_block(text: str) -> dict | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    snippet = text[start : end + 1]
    try:
        return json.loads(snippet)
    except json.JSONDecodeError:
        return None


def _normalize_line(text: str) -> str:
    return " ".join(text.strip().split())


def _normalize_block_reason(value: object) -> str:
    normalized = _normalize_line(str(value or "")).upper()
    if not normalized:
        return PLANNER_BLOCK_REASON_SAFE
    if normalized in PLANNER_BLOCK_REASONS:
        return normalized
    return PLANNER_BLOCK_REASON_SAFE


def _planner_block_message(block_reason: str, extra_notes: str) -> str:
    _ = block_reason, extra_notes
    return (
        "Не удалось обработать запрос. Такое может произойти, если загружено не фото интерьера, "
        "изображение недостаточно читаемое, запрос содержит неподдерживаемые изменения или "
        "сработали ограничения безопасности. Попробуйте загрузить другое фото или изменить запрос. "
        "Если считаете, что все было корректно, напишите на owner@vizuai.example — мы проверим ситуацию."
    )


def _build_ranker_user_text(
    user_request: str,
    must_not_change: list[str],
    style_reference_enabled: bool = False,
) -> str:
    anchors = [item for item in must_not_change if isinstance(item, str) and item.strip()]
    anchors_json = json.dumps(anchors, ensure_ascii=False)
    request_line = _normalize_line(user_request or "")
    lines = [
        f"user_request: {request_line}",
        f"must_not_change: {anchors_json}",
        f"style_reference_enabled: {'true' if style_reference_enabled else 'false'}",
        "Image 1: original_photo (reference image used for edits)",
        "Image 2: candidate_A",
        "Image 3: candidate_B",
    ]
    if style_reference_enabled:
        lines.append("Image 4: style_reference")
    return "\n".join(lines)


def _parse_planner_payload(text: str) -> tuple[PlannerResult, str]:
    payload = _extract_json_block(text)
    if not payload:
        return _parse_planner_text_fallback(text), "text_fallback"
    methods = [
        str(item).strip()
        for item in payload.get("methods", [])
        if str(item).strip() in PLANNER_METHOD_IDS
    ]
    block_reason = _normalize_block_reason(payload.get("block_reason"))
    room_type = _normalize_line(str(payload.get("room_type", ""))) or "room"
    target_style = _normalize_line(str(payload.get("target_style", ""))) or "modern"
    must_not_change = [
        _normalize_line(str(item))
        for item in payload.get("must_not_change", [])
        if _normalize_line(str(item))
    ]
    compiled_prompt = _normalize_line(str(payload.get("planner_compiled_prompt", "")))
    if not compiled_prompt:
        compiled_prompt = _normalize_line(payload.get("extra_notes") or "") or "Improve the room based on the request."
    extra_notes = _normalize_line(str(payload.get("extra_notes", "")))
    return (
        PlannerResult(
            block_reason=block_reason,
            methods=methods,
            room_type=room_type,
            target_style=target_style,
            must_not_change=must_not_change,
            planner_compiled_prompt=compiled_prompt,
            extra_notes=extra_notes,
        ),
        "json",
    )


def _split_items(value: str) -> list[str]:
    if not value:
        return []
    normalized = value.replace("\r", "\n").replace(";", ",")
    items: list[str] = []
    for line in normalized.splitlines():
        line = line.strip()
        if not line:
            continue
        line = line.lstrip("-*").strip()
        if not line:
            continue
        for part in line.split(","):
            part = part.strip().strip("\"'`")
            part = part.strip("[]")
            part = part.strip()
            if not part or part in {"-", "—"}:
                continue
            items.append(part)
    # keep order, dedupe
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _parse_planner_text_fallback(text: str) -> PlannerResult:
    raw = text or ""
    normalized_raw = _normalize_line(raw)
    if not normalized_raw:
        raise ValueError("Planner returned empty text.")

    keys = {
        "block_reason",
        "methods",
        "room_type",
        "target_style",
        "must_not_change",
        "planner_compiled_prompt",
        "extra_notes",
    }
    fields: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            fields[current_key] = "\n".join(current_lines).strip()
        current_key = None
        current_lines = []

    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if ":" in line:
            left, right = line.split(":", 1)
            key = left.strip().lower().replace(" ", "_")
            if key in keys:
                flush()
                current_key = key
                current_lines = [right.strip()]
                continue
        if current_key is not None:
            current_lines.append(line)
    flush()

    methods = [
        item.strip().lower()
        for item in _split_items(fields.get("methods", ""))
        if item.strip().lower() in PLANNER_METHOD_IDS
    ]
    block_reason = _normalize_block_reason(fields.get("block_reason", ""))
    room_type = _normalize_line(fields.get("room_type", "")) or "room"
    target_style = _normalize_line(fields.get("target_style", "")) or "modern"
    must_not_change = _split_items(fields.get("must_not_change", ""))
    compiled_prompt = _normalize_line(fields.get("planner_compiled_prompt", ""))
    extra_notes = _normalize_line(fields.get("extra_notes", ""))
    if not compiled_prompt:
        compiled_prompt = extra_notes or normalized_raw

    if not compiled_prompt:
        raise ValueError("Planner text fallback produced empty prompt.")

    return PlannerResult(
        block_reason=block_reason,
        methods=methods,
        room_type=room_type,
        target_style=target_style,
        must_not_change=must_not_change,
        planner_compiled_prompt=compiled_prompt,
        extra_notes=extra_notes,
    )


def _parse_validator_payload(text: str) -> tuple[ValidationResult, str]:
    payload = _extract_json_block(text)
    if not payload:
        return (
            ValidationResult(
                request_ok=False,
                geometry_ok=False,
                function_ok=False,
                scores={"request": 0, "geometry": 0, "function": 0},
                notes=_normalize_line(text)[:500] or "invalid_json",
            ),
            "invalid_json",
        )
    scores = payload.get("scores") or {}
    def _score(value: object) -> int:
        try:
            return max(0, min(100, int(value)))
        except Exception:
            return 0
    result = ValidationResult(
        request_ok=bool(payload.get("request_ok")),
        geometry_ok=bool(payload.get("geometry_ok")),
        function_ok=bool(payload.get("function_ok")),
        scores={
            "request": _score(scores.get("request")),
            "geometry": _score(scores.get("geometry")),
            "function": _score(scores.get("function")),
        },
        notes=_normalize_line(str(payload.get("notes", ""))) or "",
    )
    return result, "json"


def _parse_ranker_payload(text: str) -> tuple[dict[str, Any], str]:
    payload = _extract_json_block(text)
    if not isinstance(payload, dict):
        raise ValueError("Ranker returned invalid JSON object.")
    return payload, "json"


def _normalize_ranker_best(raw: object) -> str:
    value = str(raw or "").strip().upper()
    if value in {"A", "B", "TIE"}:
        return value
    aliases = {
        "CANDIDATE_A": "A",
        "CANDIDATE B": "B",
        "CANDIDATE_B": "B",
        "OPTION_A": "A",
        "OPTION_B": "B",
        "RENDER": "A",
        "RERENDER": "B",
    }
    return aliases.get(value, "")


def _extract_ranker_candidate(payload: dict[str, Any], label: str) -> dict[str, Any] | None:
    keys = (
        ("A", "a", "candidate_a", "candidateA", "option_a", "render")
        if label == "A"
        else ("B", "b", "candidate_b", "candidateB", "option_b", "rerender")
    )
    for key in keys:
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            return candidate
    return None


def _normalize_ranker_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "best": _normalize_ranker_best(payload.get("best") or payload.get("winner")),
        "confidence": payload.get("confidence"),
        "both_failed": payload.get("both_failed"),
        "A": _extract_ranker_candidate(payload, "A"),
        "B": _extract_ranker_candidate(payload, "B"),
        "decision": payload.get("decision") if isinstance(payload.get("decision"), dict) else None,
    }


def _validation_from_ranker_candidate(
    candidate: object,
    fallback_notes: str,
) -> ValidationResult:
    data = candidate if isinstance(candidate, dict) else {}
    geometry = data.get("geometry") if isinstance(data.get("geometry"), dict) else {}
    request = data.get("request") if isinstance(data.get("request"), dict) else {}
    function = data.get("function") if isinstance(data.get("function"), dict) else {}
    def _score_1_5(value: object) -> int:
        try:
            return max(1, min(5, int(value)))
        except Exception:
            return 1

    g_items = [
        _score_1_5(geometry.get("must_not_change_integrity")),
        _score_1_5(geometry.get("camera_fov")),
        _score_1_5(geometry.get("planes_perspective")),
        _score_1_5(geometry.get("inwall_furniture")),
    ]
    geometry_score = int(round((sum(g_items) / 20.0) * 100.0))
    request_fit = _score_1_5(request.get("request_fit"))
    request_score = request_fit * 20
    circulation_ok = bool(function.get("circulation_ok"))
    access_ok = bool(function.get("access_ok"))
    function_score = (50 if circulation_ok else 0) + (50 if access_ok else 0)
    notes = _normalize_line(
        str(
            (
                data.get("decision_reason")
                or (data.get("geometry") or {}).get("violations")
                or fallback_notes
            )
        )
    )
    return ValidationResult(
        request_ok=bool(request.get("request_ok")),
        geometry_ok=min(g_items) >= 3,
        function_ok=circulation_ok and access_ok,
        scores={
            "request": request_score,
            "geometry": geometry_score,
            "function": function_score,
        },
        notes=notes or fallback_notes,
    )


def _overall_score(scores: dict[str, int]) -> int:
    return scores.get("geometry", 0) * 10000 + scores.get("request", 0) * 100 + scores.get("function", 0)


def _add_usage(a: dict | None, b: dict | None) -> dict | None:
    if not a and not b:
        return None
    base = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for usage in (a, b):
        if not isinstance(usage, dict):
            continue
        for key in base:
            value = usage.get(key)
            if isinstance(value, int):
                base[key] += value
    return base


def _sum_cost_values(*values: object) -> float | None:
    total = 0.0
    found = False
    for value in values:
        if isinstance(value, (int, float)):
            total += float(value)
            found = True
    if not found:
        return None
    return total


def _split_cost_evenly(value: float | None, parts: int) -> list[float | None]:
    if parts <= 0:
        return []
    if value is None:
        return [None for _ in range(parts)]
    per_part = float(value) / float(parts)
    return [per_part for _ in range(parts)]


async def _validator_with_empty_retry(
    settings: Settings,
    instruction: str,
    user_text: str,
    images: list[bytes],
    max_output_tokens: int,
    temperature: float | None,
    reasoning_effort: str,
    text_verbosity: str,
    store: bool | None,
    gemini_temperature: float,
    stage: str,
    logger,
    job_id: str | None,
) -> tuple[str, str, dict | None, float | None, list[dict[str, Any]], dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    total_usage: dict | None = None
    total_cost: float | None = None
    prompt = instruction
    validator_schema = _validator_output_schema()
    schema_requested = True
    schema_applied = False
    schema_fallback_reason: str | None = None

    for attempt in range(1, 3):
        text, provider, usage, cost, llm_meta = await _llm_text_with_fallback(
            settings=settings,
            instruction=prompt,
            user_text=user_text,
            images=images,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
            store=store,
            gemini_temperature=gemini_temperature,
            output_schema=validator_schema,
            output_schema_name=f"{stage}_result",
        )
        schema_requested = schema_requested or bool(llm_meta.get("output_schema_requested"))
        schema_applied = schema_applied or bool(llm_meta.get("output_schema_applied"))
        if not schema_fallback_reason and isinstance(llm_meta.get("schema_fallback_reason"), str):
            schema_fallback_reason = str(llm_meta.get("schema_fallback_reason"))
        normalized = _normalize_line(text)
        is_empty = not normalized
        has_json = _extract_json_block(text) is not None
        attempts.append(
            {
                "attempt": attempt,
                "provider": provider,
                "is_empty": is_empty,
                "has_json": has_json,
                "chars": len(text or ""),
                "usage": usage,
                "cost_usd": cost,
                "llm_meta": llm_meta,
            }
        )
        total_usage = _add_usage(total_usage, usage)
        if isinstance(cost, (int, float)):
            total_cost = float(cost) if total_cost is None else total_cost + float(cost)

        if not is_empty:
            schema_meta = {
                "requested": schema_requested,
                "applied": schema_applied,
                "fallback_reason": schema_fallback_reason,
            }
            return text, provider, total_usage, total_cost, attempts, schema_meta
        if attempt == 1:
            if logger:
                logger.warning(
                    "simple_pipeline job=%s %s_empty_output_retry provider=%s",
                    job_id,
                    stage,
                    provider,
                )
            prompt = (
                instruction.rstrip()
                + "\n\nIMPORTANT: Return ONLY one valid JSON object that matches OUTPUT FORMAT. No prose."
            )

    last = attempts[-1]
    schema_meta = {
        "requested": schema_requested,
        "applied": schema_applied,
        "fallback_reason": schema_fallback_reason,
    }
    return (
        "",
        str(last.get("provider") or "unknown"),
        total_usage,
        total_cost,
        attempts,
        schema_meta,
    )


async def _planner_with_json_retry(
    settings: Settings,
    instruction: str,
    user_text: str,
    images: list[bytes],
    max_output_tokens: int,
    temperature: float | None,
    reasoning_effort: str,
    text_verbosity: str,
    store: bool | None,
    gemini_temperature: float,
    logger,
    job_id: str | None,
) -> tuple[
    str,
    PlannerResult | None,
    str,
    dict | None,
    float | None,
    list[dict[str, Any]],
    str | None,
    str | None,
    bool,
    dict[str, Any],
]:
    attempts: list[dict[str, Any]] = []
    total_usage: dict | None = None
    total_cost: float | None = None
    prompt = instruction
    planner_schema = _planner_output_schema()

    last_text = ""
    last_provider = "unknown"
    last_error = "unknown"
    schema_requested = True
    schema_applied = False
    schema_fallback_reason: str | None = None
    parse_mode: str | None = None
    text_fallback_used = False

    for attempt in range(1, 3):
        text, provider, usage, cost, llm_meta = await _llm_text_with_fallback(
            settings=settings,
            instruction=prompt,
            user_text=user_text,
            images=images,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
            store=store,
            gemini_temperature=gemini_temperature,
            output_schema=planner_schema,
            output_schema_name="planner_result",
        )
        last_text = text or ""
        last_provider = provider
        total_usage = _add_usage(total_usage, usage)
        if isinstance(cost, (int, float)):
            total_cost = float(cost) if total_cost is None else total_cost + float(cost)
        schema_requested = schema_requested or bool(llm_meta.get("output_schema_requested"))
        schema_applied = schema_applied or bool(llm_meta.get("output_schema_applied"))
        if not schema_fallback_reason and isinstance(llm_meta.get("schema_fallback_reason"), str):
            schema_fallback_reason = str(llm_meta.get("schema_fallback_reason"))

        parse_error = ""
        parsed: PlannerResult | None = None
        current_parse_mode: str | None = None
        try:
            parsed, current_parse_mode = _parse_planner_payload(last_text)
            parse_mode = current_parse_mode
            text_fallback_used = current_parse_mode == "text_fallback"
        except Exception as exc:
            parse_error = str(exc)
            last_error = parse_error

        attempts.append(
            {
                "attempt": attempt,
                "provider": provider,
                "chars": len(last_text),
                "has_json": _extract_json_block(last_text) is not None,
                "usage": usage,
                "cost_usd": cost,
                "parse_error": parse_error or None,
                "parse_mode": current_parse_mode,
                "parse_via_text_fallback": current_parse_mode == "text_fallback",
                "schema_requested": bool(llm_meta.get("output_schema_requested")),
                "schema_applied": bool(llm_meta.get("output_schema_applied")),
                "schema_fallback_reason": llm_meta.get("schema_fallback_reason"),
            }
        )

        if parsed is not None:
            planner_schema_meta = {
                "requested": schema_requested,
                "applied": schema_applied,
                "fallback_reason": schema_fallback_reason,
            }
            return (
                last_text,
                parsed,
                provider,
                total_usage,
                total_cost,
                attempts,
                None,
                parse_mode,
                text_fallback_used,
                planner_schema_meta,
            )

        if attempt == 1:
            if logger:
                logger.warning(
                    "simple_pipeline job=%s planner_invalid_json_retry provider=%s",
                    job_id,
                    provider,
                )
            prompt = (
                instruction.rstrip()
                + "\n\nIMPORTANT: Return ONLY one valid JSON object that matches OUTPUT FORMAT. No prose, no markdown, no bullet list."
            )

    error = (
        f"Planner returned invalid JSON after retries "
        f"(provider={last_provider}, error={last_error}, chars={len(last_text)})"
    )
    planner_schema_meta = {
        "requested": schema_requested,
        "applied": schema_applied,
        "fallback_reason": schema_fallback_reason,
    }
    return (
        last_text,
        None,
        last_provider,
        total_usage,
        total_cost,
        attempts,
        error,
        parse_mode,
        text_fallback_used,
        planner_schema_meta,
    )


async def _ranker_with_json_retry(
    settings: Settings,
    instruction: str,
    user_text: str,
    images: list[bytes],
    max_output_tokens: int,
    temperature: float | None,
    reasoning_effort: str,
    text_verbosity: str,
    store: bool | None,
    gemini_temperature: float,
    logger,
    job_id: str | None,
) -> tuple[
    str,
    dict[str, Any] | None,
    str,
    dict | None,
    float | None,
    list[dict[str, Any]],
    str | None,
    str | None,
    dict[str, Any],
]:
    attempts: list[dict[str, Any]] = []
    total_usage: dict | None = None
    total_cost: float | None = None
    prompt = instruction
    ranker_schema = _ranker_output_schema()

    last_text = ""
    last_provider = "unknown"
    last_error = "unknown"
    schema_requested = True
    schema_applied = False
    schema_fallback_reason: str | None = None
    parse_mode: str | None = None

    for attempt in range(1, 3):
        text, provider, usage, cost, llm_meta = await _llm_text_with_fallback(
            settings=settings,
            instruction=prompt,
            user_text=user_text,
            images=images,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
            store=store,
            gemini_temperature=gemini_temperature,
            output_schema=ranker_schema,
            output_schema_name="ranker_ab_result",
        )
        last_text = text or ""
        last_provider = provider
        total_usage = _add_usage(total_usage, usage)
        if isinstance(cost, (int, float)):
            total_cost = float(cost) if total_cost is None else total_cost + float(cost)
        schema_requested = schema_requested or bool(llm_meta.get("output_schema_requested"))
        schema_applied = schema_applied or bool(llm_meta.get("output_schema_applied"))
        if not schema_fallback_reason and isinstance(llm_meta.get("schema_fallback_reason"), str):
            schema_fallback_reason = str(llm_meta.get("schema_fallback_reason"))

        parse_error = ""
        parsed: dict[str, Any] | None = None
        current_parse_mode: str | None = None
        try:
            parsed, current_parse_mode = _parse_ranker_payload(last_text)
            parse_mode = current_parse_mode
        except Exception as exc:
            parse_error = str(exc)
            last_error = parse_error

        attempts.append(
            {
                "attempt": attempt,
                "provider": provider,
                "chars": len(last_text),
                "has_json": _extract_json_block(last_text) is not None,
                "usage": usage,
                "cost_usd": cost,
                "parse_error": parse_error or None,
                "parse_mode": current_parse_mode,
                "schema_requested": bool(llm_meta.get("output_schema_requested")),
                "schema_applied": bool(llm_meta.get("output_schema_applied")),
                "schema_fallback_reason": llm_meta.get("schema_fallback_reason"),
            }
        )

        if parsed is not None:
            ranker_schema_meta = {
                "requested": schema_requested,
                "applied": schema_applied,
                "fallback_reason": schema_fallback_reason,
            }
            return (
                last_text,
                parsed,
                provider,
                total_usage,
                total_cost,
                attempts,
                None,
                parse_mode,
                ranker_schema_meta,
            )

        if attempt == 1:
            if logger:
                logger.warning(
                    "simple_pipeline job=%s ranker_invalid_json_retry provider=%s",
                    job_id,
                    provider,
                )
            prompt = (
                instruction.rstrip()
                + "\n\nIMPORTANT: Return ONLY one valid JSON object with exact schema. No prose, no markdown."
            )

    error = (
        f"Ranker returned invalid JSON after retries "
        f"(provider={last_provider}, error={last_error}, chars={len(last_text)})"
    )
    ranker_schema_meta = {
        "requested": schema_requested,
        "applied": schema_applied,
        "fallback_reason": schema_fallback_reason,
    }
    return (
        last_text,
        None,
        last_provider,
        total_usage,
        total_cost,
        attempts,
        error,
        parse_mode,
        ranker_schema_meta,
    )


def _assemble_render_prompt(
    template: str,
    planner: PlannerResult,
) -> str:
    must_not_change = "; ".join(planner.must_not_change) if planner.must_not_change else "none"
    prompt = template.replace("<TARGET_STYLE>", planner.target_style)
    prompt = prompt.replace("<must_not_change>", must_not_change)
    prompt = prompt.replace("<planner_compiled_prompt>", planner.planner_compiled_prompt)
    return prompt


def _openai_image_part(image_bytes: bytes) -> dict:
    mime = "image/png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return {"type": "input_image", "image_url": f"data:{mime};base64,{b64}"}


def _build_openai_headers(settings: Settings, api_key: str, *, json_content: bool) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    if json_content:
        headers["Content-Type"] = "application/json"
    organization = str(settings.OPENAI_ORGANIZATION or "").strip()
    project = str(settings.OPENAI_PROJECT or "").strip()
    if organization:
        headers["OpenAI-Organization"] = organization
    if project:
        headers["OpenAI-Project"] = project
    return headers


def _extract_openai_response_meta(response: aiohttp.ClientResponse) -> dict[str, Any]:
    relevant_headers = (
        "x-request-id",
        "x-envoy-upstream-service-time",
        "openai-processing-ms",
        "x-ratelimit-limit-requests",
        "x-ratelimit-remaining-requests",
        "x-ratelimit-reset-requests",
        "x-ratelimit-limit-tokens",
        "x-ratelimit-remaining-tokens",
        "x-ratelimit-reset-tokens",
        "retry-after",
    )
    headers: dict[str, str] = {}
    for key in relevant_headers:
        value = response.headers.get(key)
        if value:
            headers[key] = value
    return {
        "status": response.status,
        "headers": headers,
    }


class _RetryableOpenAIRequestError(RuntimeError):
    def __init__(
        self,
        *,
        status: int,
        message: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.status = int(status)
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"OpenAI retryable error {status}: {message}")

    def retry_delay_seconds(self, attempt: int) -> float:
        if isinstance(self.retry_after_seconds, (int, float)) and self.retry_after_seconds > 0:
            return min(float(self.retry_after_seconds), 8.0)
        return min(4.0, 0.75 * (2 ** max(attempt - 1, 0)))


def _parse_retry_after_seconds(value: str | None) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = float(raw)
    except Exception:
        return None
    if parsed < 0:
        return None
    return parsed


def _extract_openai_text(payload: dict) -> str:
    for item in payload.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                return text
    return payload.get("output_text", "").strip()


def _extract_openai_usage(payload: dict) -> dict:
    usage = payload.get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _extract_openai_image_usage(payload: dict) -> dict[str, Any] | None:
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return None
    normalized: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "image_count",
        "cost_usd",
        "total_cost_usd",
    ):
        if key in usage:
            normalized[key] = usage.get(key)
    # Keep nested usage details if API returns them.
    for key in ("input_tokens_details", "output_tokens_details"):
        if isinstance(usage.get(key), dict):
            normalized[key] = usage.get(key)
    for key, value in usage.items():
        if key not in normalized:
            normalized[key] = value
    return normalized or None


def _compute_gpt52_cost(usage: dict) -> float | None:
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return None
    return (input_tokens / 1_000_000) * 1.75 + (output_tokens / 1_000_000) * 14.0


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


def _image_price_from_table(settings: Settings, size: str, quality: str) -> float | None:
    raw = settings.OPENAI_IMAGE_PRICE_TABLE_JSON
    if not raw:
        return None
    try:
        table = json.loads(raw)
    except Exception:
        return None
    if not isinstance(table, dict):
        return None

    normalized_quality = (quality or "").strip().lower()
    size_key = str(size or "").strip().lower()
    keys = [
        f"{size_key}:{normalized_quality}",
        f"{size_key}|{normalized_quality}",
        size_key,
    ]
    for key in keys:
        value = table.get(key)
        price = _to_float_or_none(value)
        if price is not None and price >= 0:
            return price
    return None


def _compute_gpt_image_cost(
    settings: Settings, usage: dict[str, Any] | None, size: str, quality: str
) -> tuple[float | None, str | None]:
    usage_payload = usage or {}
    explicit_cost = _to_float_or_none(
        usage_payload.get("cost_usd") or usage_payload.get("total_cost_usd")
    )
    if explicit_cost is not None and explicit_cost >= 0:
        return explicit_cost, "usage_cost_field"

    input_tokens = _to_float_or_none(usage_payload.get("input_tokens"))
    output_tokens = _to_float_or_none(usage_payload.get("output_tokens"))
    in_price = settings.OPENAI_IMAGE_INPUT_PRICE_PER_MILLION
    out_price = settings.OPENAI_IMAGE_OUTPUT_PRICE_PER_MILLION
    if (
        input_tokens is not None
        and output_tokens is not None
        and isinstance(in_price, (int, float))
        and isinstance(out_price, (int, float))
    ):
        cost = (input_tokens / 1_000_000) * float(in_price) + (output_tokens / 1_000_000) * float(out_price)
        return cost, "usage_tokens"

    table_price = _image_price_from_table(settings, size=size, quality=quality)
    if table_price is not None:
        return table_price, "price_table"

    return None, None


async def _openai_text_with_usage(
    settings: Settings,
    api_key: str,
    model: str,
    system_text: str,
    user_text: str,
    images: list[bytes],
    max_output_tokens: int,
    timeout_seconds: int,
    temperature: float | None,
    reasoning_effort: str | None,
    text_verbosity: str | None,
    store: bool | None,
    output_schema: dict | None = None,
    output_schema_name: str = "structured_output",
) -> tuple[str, dict, dict[str, Any]]:
    url = "https://api.openai.com/v1/responses"
    headers = _build_openai_headers(settings, api_key, json_content=True)
    user_content: list[dict] = [{"type": "input_text", "text": user_text}]
    for image in images:
        user_content.append(_openai_image_part(image))
    payload: dict = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_text}]},
            {"role": "user", "content": user_content},
        ],
        "max_output_tokens": max_output_tokens,
    }
    text_payload: dict[str, Any] = {}
    if temperature is not None and not model.startswith("gpt-5"):
        payload["temperature"] = temperature
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    if text_verbosity:
        text_payload["verbosity"] = text_verbosity
    if output_schema:
        text_payload["format"] = {
            "type": "json_schema",
            "name": output_schema_name,
            "schema": output_schema,
            "strict": True,
        }
    if text_payload:
        payload["text"] = text_payload
    if store is not None:
        payload["store"] = store

    async def _post(data: dict) -> tuple[dict, dict[str, Any]]:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, headers=headers, json=data) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    if response.status in {408, 409, 429} or response.status >= 500:
                        raise _RetryableOpenAIRequestError(
                            status=response.status,
                            message=error_text,
                            retry_after_seconds=_parse_retry_after_seconds(
                                response.headers.get("retry-after")
                            ),
                        )
                    raise RuntimeError(f"OpenAI error {response.status}: {error_text}")
                response_meta = _extract_openai_response_meta(response)
                return await response.json(), response_meta

    async def _post_with_transport_retry(data: dict) -> tuple[dict, dict[str, Any]]:
        attempts = 4
        for attempt in range(1, attempts + 1):
            try:
                return await _post(data)
            except _RetryableOpenAIRequestError as exc:
                if attempt == attempts:
                    raise RuntimeError(str(exc)) from exc
                await asyncio.sleep(exc.retry_delay_seconds(attempt))
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
                if attempt == attempts:
                    raise
                # Exponential backoff with a small cap keeps retries fast for transient socket issues.
                await asyncio.sleep(min(2.0, 0.5 * (2 ** (attempt - 1))))
        raise RuntimeError("OpenAI request retry loop exhausted")

    schema_requested = bool(output_schema)
    schema_applied = schema_requested
    schema_fallback_reason: str | None = None
    response_meta: dict[str, Any] | None = None

    try:
        data, response_meta = await _post_with_transport_retry(payload)
    except RuntimeError as exc:
        message = str(exc)
        if "Unsupported parameter" in message and "temperature" in message:
            payload.pop("temperature", None)
            data, response_meta = await _post_with_transport_retry(payload)
        elif output_schema and (
            "Unsupported parameter" in message
            or "text.format" in message
            or "json_schema" in message
            or "Invalid schema" in message
            or "invalid_request_error" in message
        ):
            fallback_payload = dict(payload)
            fallback_payload.pop("text", None)
            if text_verbosity:
                fallback_payload["text"] = {"verbosity": text_verbosity}
            data, response_meta = await _post_with_transport_retry(fallback_payload)
            schema_applied = False
            schema_fallback_reason = "schema_unsupported_or_invalid"
        else:
            raise
    meta = {
        "output_schema_requested": schema_requested,
        "output_schema_applied": schema_applied,
        "schema_fallback_reason": schema_fallback_reason,
        "openai_response": response_meta,
        "openai_request_headers": {
            "organization_set": bool(settings.OPENAI_ORGANIZATION),
            "project_set": bool(settings.OPENAI_PROJECT),
            "organization": settings.OPENAI_ORGANIZATION,
            "project": settings.OPENAI_PROJECT,
        },
    }
    return _extract_openai_text(data), _extract_openai_usage(data), meta


async def _openai_text(
    settings: Settings,
    api_key: str,
    model: str,
    system_text: str,
    user_text: str,
    images: list[bytes],
    max_output_tokens: int,
    timeout_seconds: int,
    temperature: float | None,
    reasoning_effort: str | None,
    text_verbosity: str | None,
    store: bool | None,
) -> str:
    text, _, _ = await _openai_text_with_usage(
        settings=settings,
        api_key=api_key,
        model=model,
        system_text=system_text,
        user_text=user_text,
        images=images,
        max_output_tokens=max_output_tokens,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        text_verbosity=text_verbosity,
        store=store,
    )
    return text


def _guess_mime_type(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "image/jpeg"


async def _gemini_text(
    project_id: str,
    location: str,
    credentials_path: str | None,
    model: str,
    instruction: str,
    user_text: str,
    images: list[bytes],
    timeout_seconds: int,
    max_output_tokens: int,
    temperature: float,
) -> str:
    if credentials_path and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
    from google import genai
    from google.genai import types

    client = genai.Client(vertexai=True, project=project_id, location=location)
    contents: list[object] = [instruction]
    if user_text.strip():
        contents.append(_normalize_line(user_text))
    for image in images:
        contents.append(types.Part.from_bytes(data=image, mime_type=_guess_mime_type(image)))
    response = await asyncio.wait_for(
        asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                response_mime_type="text/plain",
            ),
        ),
        timeout=timeout_seconds,
    )
    return _normalize_line(_extract_vertex_text(response))


def _extract_vertex_text(response: object) -> str:
    parts = getattr(response, "parts", None)
    if not parts:
        candidates = getattr(response, "candidates", None)
        if candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None)
    if not parts:
        return ""
    texts = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts).strip()


async def _openai_image_edit(
    settings: Settings,
    api_key: str,
    model: str,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    prompt: str,
    size: str,
    timeout_seconds: int,
    quality: str,
    output_format: str,
    background: str,
    moderation: str,
    partial_images: int,
) -> tuple[bytes, dict[str, Any] | None, float | None, str | None, dict[str, Any] | None]:
    batch = await _openai_image_edit_batch(
        settings=settings,
        api_key=api_key,
        model=model,
        image_bytes=image_bytes,
        aux_image_bytes=aux_image_bytes,
        prompt=prompt,
        size=size,
        timeout_seconds=timeout_seconds,
        quality=quality,
        output_format=output_format,
        background=background,
        moderation=moderation,
        partial_images=partial_images,
        n=1,
    )
    return batch.images[0], batch.usage, batch.cost_usd, batch.cost_source, batch.request_meta


def _openai_image_client_timeout(settings: Settings) -> aiohttp.ClientTimeout:
    total = max(1, int(settings.OPENAI_IMAGE_TIMEOUT))
    connect = max(1, int(settings.OPENAI_IMAGE_TIMEOUT_CONNECT_SECONDS))
    sock_read = max(1, int(settings.OPENAI_IMAGE_TIMEOUT_READ_SECONDS))
    return aiohttp.ClientTimeout(
        total=total,
        connect=connect,
        sock_connect=connect,
        sock_read=sock_read,
    )


async def _openai_image_edit_batch(
    settings: Settings,
    api_key: str,
    model: str,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    prompt: str,
    size: str,
    timeout_seconds: int,
    quality: str,
    output_format: str,
    background: str,
    moderation: str,
    partial_images: int,
    n: int,
) -> ImageBatchCallResult:
    url = "https://api.openai.com/v1/images/edits"
    headers = _build_openai_headers(settings, api_key, json_content=False)
    primary_bytes, primary_filename, primary_content_type, primary_meta = _prepare_openai_edit_transport(
        image_bytes,
        max_long_edge=settings.OPENAI_IMAGE_INPUT_MAX_LONG_EDGE,
        preferred_format=settings.OPENAI_IMAGE_INPUT_FORMAT,
        jpeg_quality=settings.OPENAI_IMAGE_INPUT_JPEG_QUALITY,
        filename_stem="input",
    )
    aux_transport_meta: dict[str, Any] | None = None
    form = aiohttp.FormData()
    form.add_field("model", model)
    form.add_field("prompt", prompt)
    if aux_image_bytes:
        aux_bytes, aux_filename, aux_content_type, aux_transport_meta = _prepare_openai_edit_transport(
            aux_image_bytes,
            max_long_edge=settings.OPENAI_IMAGE_AUX_MAX_LONG_EDGE,
            preferred_format=settings.OPENAI_IMAGE_INPUT_FORMAT,
            jpeg_quality=settings.OPENAI_IMAGE_INPUT_JPEG_QUALITY,
            filename_stem="input_aux",
        )
        form.add_field("image[]", primary_bytes, filename=primary_filename, content_type=primary_content_type)
        form.add_field("image[]", aux_bytes, filename=aux_filename, content_type=aux_content_type)
    else:
        form.add_field("image", primary_bytes, filename=primary_filename, content_type=primary_content_type)
    form.add_field("n", str(n))
    form.add_field("size", size)
    form.add_field("quality", quality)
    form.add_field("input_fidelity", settings.OPENAI_IMAGE_INPUT_FIDELITY)
    form.add_field("output_format", output_format)
    form.add_field("background", background)
    form.add_field("moderation", moderation)
    form.add_field("partial_images", str(partial_images))
    timeout = _openai_image_client_timeout(settings)
    response_meta: dict[str, Any] | None = None
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, headers=headers, data=form) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise RuntimeError(f"OpenAI error {response.status}: {error_text}")
            response_meta = _extract_openai_response_meta(response)
            payload = await response.json()
    data = payload.get("data", [])
    if not data:
        raise ValueError("OpenAI response has no image data.")
    images: list[bytes] = []
    for idx, item in enumerate(data[:n]):
        b64_data = item.get("b64_json")
        if not b64_data:
            raise ValueError(f"OpenAI response missing b64_json for image #{idx + 1}.")
        images.append(base64.b64decode(b64_data))
    if len(images) != n:
        raise ValueError(f"OpenAI response returned {len(images)} images, expected {n}.")
    usage = _extract_openai_image_usage(payload)
    cost, cost_source = _compute_gpt_image_cost(
        settings=settings,
        usage=usage,
        size=size,
        quality=quality,
    )
    return ImageBatchCallResult(
        images=images,
        usage=usage,
        cost_usd=cost,
        cost_source=cost_source,
        request_meta={
            "request_timeout_seconds": timeout_seconds,
            "timeout_total_seconds": timeout.total,
            "timeout_connect_seconds": timeout.connect,
            "timeout_read_seconds": timeout.sock_read,
            "openai_response": response_meta,
            "openai_request_headers": {
                "organization_set": bool(settings.OPENAI_ORGANIZATION),
                "project_set": bool(settings.OPENAI_PROJECT),
                "organization": settings.OPENAI_ORGANIZATION,
                "project": settings.OPENAI_PROJECT,
            },
            "primary": primary_meta,
            "aux": aux_transport_meta,
            "output_format": output_format,
            "requested_images": n,
            "requested_size": size,
            "quality": quality,
        },
    )


async def _download_image_bytes(url: str, timeout: aiohttp.ClientTimeout) -> bytes:
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            if response.status >= 400:
                error_text = await response.text()
                raise RuntimeError(f"Image download error {response.status}: {error_text}")
            return await response.read()


async def _render_pair_decor8(
    settings: Settings,
    decor8: Decor8Service,
    input_image_url: str | None,
    room_type: str,
    design_style: str,
    prompt: str,
    design_style_image_url: str | None = None,
    logger=None,
    job_id: str | None = None,
) -> ImagePairCallResult:
    if not input_image_url:
        raise RuntimeError("Decor8 fallback requires input_image_url.")
    if logger:
        logger.info(
            "simple_pipeline job=%s render_batch_decor8_start timeout=%ss",
            job_id,
            settings.DECOR8_TIMEOUT_SECONDS,
        )
    started_at = time.perf_counter()
    payload = await decor8.generate_designs_for_room(
        input_image_url=input_image_url,
        room_type=room_type,
        design_style=design_style,
        prompt=prompt,
        num_images=2,
        num_inference_steps=75,
        design_style_image_url=design_style_image_url,
    )
    image_urls = extract_decor8_image_urls(payload)
    if len(image_urls) < 2:
        raise RuntimeError(f"Decor8 returned {len(image_urls)} image urls, expected 2.")
    download_timeout = aiohttp.ClientTimeout(
        total=max(float(settings.DECOR8_TIMEOUT_SECONDS or 120), 1.0),
        connect=max(float(settings.DECOR8_TIMEOUT_CONNECT_SECONDS or 15), 0.5),
        sock_read=max(float(settings.DECOR8_TIMEOUT_READ_SECONDS or 110), 0.5),
    )
    image_a, image_b = await asyncio.gather(
        _download_image_bytes(image_urls[0], download_timeout),
        _download_image_bytes(image_urls[1], download_timeout),
    )
    elapsed = time.perf_counter() - started_at
    if logger:
        logger.info(
            "simple_pipeline job=%s render_batch_decor8_done elapsed=%.2fs",
            job_id,
            elapsed,
        )
    request_meta = {
        "api_base": settings.DECOR8_API_BASE,
        "requested_images": 2,
        "room_type": room_type,
        "design_style": design_style,
        "input_image_url_present": True,
        "design_style_image_url_present": bool(design_style_image_url),
        "returned_image_urls_count": len(image_urls),
        "elapsed_seconds": round(elapsed, 3),
    }
    return ImagePairCallResult(
        candidate_a=ImageCallResult(
            image_bytes=image_a,
            provider="decor8",
            request_meta=request_meta,
        ),
        candidate_b=ImageCallResult(
            image_bytes=image_b,
            provider="decor8",
            request_meta=request_meta,
        ),
        usage=None,
        cost_usd=None,
        cost_source=None,
        request_meta=request_meta,
    )


async def _render_pair_primary_openai_with_retry(
    settings: Settings,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    prompt: str,
    size: str,
    logger=None,
    job_id: str | None = None,
) -> ImagePairCallResult:
    last_exc: Exception | None = None
    for attempt in (1, 2):
        try:
            return await _render_pair_primary_openai(
                settings=settings,
                image_bytes=image_bytes,
                aux_image_bytes=aux_image_bytes,
                prompt=prompt,
                size=size,
            )
        except Exception as exc:
            last_exc = exc
            if attempt >= 2:
                raise
            if logger:
                logger.warning(
                    "simple_pipeline job=%s render_batch_openai_failed attempt=%s/2 retrying=true error=%s",
                    job_id,
                    attempt,
                    _exc_debug_text(exc),
                )
            await asyncio.sleep(1.0)
    assert last_exc is not None
    raise last_exc


async def _llm_text_with_fallback(
    settings: Settings,
    instruction: str,
    user_text: str,
    images: list[bytes],
    max_output_tokens: int,
    temperature: float | None,
    reasoning_effort: str,
    text_verbosity: str,
    store: bool | None,
    gemini_temperature: float,
    output_schema: dict | None = None,
    output_schema_name: str = "structured_output",
) -> tuple[str, str, dict | None, float | None, dict[str, Any]]:
    openai_key = settings.OPENAI_API_KEY
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    try:
        text, usage, openai_meta = await _openai_text_with_usage(
            settings=settings,
            api_key=openai_key,
            model=settings.OPENAI_TEXT_MODEL,
            system_text=instruction,
            user_text=user_text,
            images=images,
            max_output_tokens=max_output_tokens,
            timeout_seconds=settings.OPENAI_TEXT_TIMEOUT,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            text_verbosity=text_verbosity,
            store=store,
            output_schema=output_schema,
            output_schema_name=output_schema_name,
        )
        cost = _compute_gpt52_cost(usage)
        return text, "gpt", usage, cost, openai_meta
    except Exception:
        text = await _gemini_text(
            project_id=settings.VERTEX_PROJECT_ID,
            location=settings.VERTEX_LOCATION,
            credentials_path=settings.GOOGLE_CLOUD_CREDENTIALS_PATH,
            model=settings.GEMINI_MODEL,
            instruction=instruction,
            user_text=user_text,
            images=images,
            timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
            max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
            temperature=gemini_temperature,
        )
        return text, "gemini", None, None, {
            "output_schema_requested": bool(output_schema),
            "output_schema_applied": False,
            "schema_fallback_reason": "provider_fallback_gemini",
        }


def _planner_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "block_reason",
            "methods",
            "room_type",
            "target_style",
            "must_not_change",
            "planner_compiled_prompt",
            "extra_notes",
        ],
        "properties": {
            "block_reason": {
                "type": "string",
                "enum": sorted(list(PLANNER_BLOCK_REASONS)),
            },
            "methods": {
                "type": "array",
                "items": {"type": "string", "enum": PLANNER_METHOD_IDS},
            },
            "room_type": {"type": "string"},
            "target_style": {"type": "string"},
            "must_not_change": {"type": "array", "items": {"type": "string"}},
            "planner_compiled_prompt": {"type": "string"},
            "extra_notes": {"type": "string"},
        },
    }


def _ranker_output_schema() -> dict[str, Any]:
    candidate_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["geometry", "request", "function", "aesthetic"],
        "properties": {
            "geometry": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "must_not_change_integrity",
                    "camera_fov",
                    "planes_perspective",
                    "inwall_furniture",
                    "violations",
                ],
                "properties": {
                    "must_not_change_integrity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "camera_fov": {"type": "integer", "minimum": 1, "maximum": 5},
                    "planes_perspective": {"type": "integer", "minimum": 1, "maximum": 5},
                    "inwall_furniture": {"type": "integer", "minimum": 1, "maximum": 5},
                    "violations": {"type": "array", "items": {"type": "string"}},
                },
            },
            "request": {
                "type": "object",
                "additionalProperties": False,
                "required": ["request_ok", "request_fit", "missing_or_wrong"],
                "properties": {
                    "request_ok": {"type": "boolean"},
                    "request_fit": {"type": "integer", "minimum": 1, "maximum": 5},
                    "missing_or_wrong": {"type": "array", "items": {"type": "string"}},
                },
            },
            "function": {
                "type": "object",
                "additionalProperties": False,
                "required": ["circulation_ok", "access_ok", "issues"],
                "properties": {
                    "circulation_ok": {"type": "boolean"},
                    "access_ok": {"type": "boolean"},
                    "issues": {"type": "array", "items": {"type": "string"}},
                },
            },
            "aesthetic": {
                "type": "object",
                "additionalProperties": False,
                "required": ["finish_quality", "issues"],
                "properties": {
                    "finish_quality": {"type": "integer", "minimum": 1, "maximum": 5},
                    "issues": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["best", "confidence", "both_failed", "A", "B", "decision"],
        "properties": {
            "best": {"type": "string", "enum": ["A", "B", "tie"]},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "both_failed": {"type": "boolean"},
            "A": candidate_schema,
            "B": candidate_schema,
            "decision": {
                "type": "object",
                "additionalProperties": False,
                "required": ["primary_reason", "tie_breakers_used"],
                "properties": {
                    "primary_reason": {"type": "string"},
                    "tie_breakers_used": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["none", "request", "function", "aesthetic"],
                        },
                    },
                },
            },
        },
    }


def _validator_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["request_ok", "geometry_ok", "function_ok", "scores", "notes"],
        "properties": {
            "request_ok": {"type": "boolean"},
            "geometry_ok": {"type": "boolean"},
            "function_ok": {"type": "boolean"},
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "required": ["request", "geometry", "function"],
                "properties": {
                    "request": {"type": "integer", "minimum": 0, "maximum": 100},
                    "geometry": {"type": "integer", "minimum": 0, "maximum": 100},
                    "function": {"type": "integer", "minimum": 0, "maximum": 100},
                },
            },
            "notes": {"type": "string"},
        },
    }


async def _render_pair_primary_openai(
    settings: Settings,
    image_bytes: bytes,
    aux_image_bytes: bytes | None,
    prompt: str,
    size: str,
) -> ImagePairCallResult:
    openai_key = settings.OPENAI_API_KEY
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    batch = await _openai_image_edit_batch(
        settings=settings,
        api_key=openai_key,
        model=settings.OPENAI_IMAGE_MODEL,
        image_bytes=image_bytes,
        aux_image_bytes=aux_image_bytes,
        prompt=prompt,
        size=size,
        timeout_seconds=settings.OPENAI_IMAGE_TIMEOUT,
        quality=settings.OPENAI_IMAGE_QUALITY,
        output_format=settings.OPENAI_IMAGE_OUTPUT_FORMAT,
        background=settings.OPENAI_IMAGE_BACKGROUND,
        moderation=settings.OPENAI_IMAGE_MODERATION,
        partial_images=settings.OPENAI_IMAGE_PARTIAL_IMAGES,
        n=2,
    )
    cost_a, cost_b = _split_cost_evenly(batch.cost_usd, 2)
    return ImagePairCallResult(
        candidate_a=ImageCallResult(
            image_bytes=batch.images[0],
            provider="gpt",
            cost_usd=cost_a,
            cost_source=batch.cost_source,
            usage=batch.usage,
            request_meta=batch.request_meta,
        ),
        candidate_b=ImageCallResult(
            image_bytes=batch.images[1],
            provider="gpt",
            cost_usd=cost_b,
            cost_source=batch.cost_source,
            usage=None,
            request_meta=batch.request_meta,
        ),
        usage=batch.usage,
        cost_usd=batch.cost_usd,
        cost_source=batch.cost_source,
        request_meta=batch.request_meta,
    )


def _exc_debug_text(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"{type(exc).__name__}: {message}"
    return f"{type(exc).__name__}: {repr(exc)}"
