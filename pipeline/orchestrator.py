"""Async pipeline orchestrator for AR interior redesign."""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from config import Settings
from models.schemas import Job, ProductResult, VisionObject
from pipeline.simple_pipeline import (
    PlannerBlockedError,
    SimplePipelineRunner,
    SimplePipelineError,
)
from services.furniture_vision_verifier import (
    FurnitureVisionVerifier,
    VerifierCandidate,
)
from services.furniture_query_terms import (
    FurnitureQueryTermsService,
    QueryTermsCropInput,
    is_delete_marker,
)
from services.db_connection import get_db_session
from services.redis_client import RuntimeStateClient
from services.repositories.design_repository import DesignRepository
from services.storage import S3Storage
from utils.furniture_label_rules import load_furniture_label_rules
from utils.image_processing import batch_crop
from utils.label_loader import load_label_set
from utils.pdf_generator import apply_numbered_overlay
from utils.response_parser import (
    SearchCandidate,
    extract_searchapi_candidates,
    parse_vision,
    rank_searchapi_candidates,
    searchapi_candidate_samples,
    searchapi_candidate_source,
    searchapi_error_message,
    searchapi_visual_matches_count,
)
from utils.retry import async_retry

MODE_RENDER_ONLY = "render_only"
MODE_FURNITURE_SEARCH = "furniture_search"


def _image_suffix_for_bytes(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    return ".jpg"


def _looks_like_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        UUID(str(value))
        return True
    except Exception:
        return False


class VisionService(Protocol):
    async def detect_objects(self, image_bytes: bytes) -> dict: ...


class SearchService(Protocol):
    async def search(
        self,
        image_url: str,
        query: str = "ozon.ru",
        *,
        marketplace: str | None = None,
        search_type: str | None = None,
        hl: str | None = None,
        country: str | None = None,
        device: str | None = None,
    ) -> dict: ...


@dataclass
class OrchestratorConfig:
    exclude_labels_path: Path = Path("data/exclude_labels.json")
    min_score: float = 0.5
    min_area: float = 0.01
    max_objects: int = 10
    prefetch_n: int = 30
    iou_threshold: float = 0.85
    containment_threshold: float = 0.90
    max_per_label: int = 2
    search_query: str = "ozon.ru"
    poll_interval: float = 3.0
    debug_dump_dir: Path | None = None


class PipelineOrchestrator:
    def __init__(
        self,
        settings: Settings,
        redis_client: RuntimeStateClient,
        storage: S3Storage,
        vision: VisionService,
        search: SearchService,
        config: OrchestratorConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._settings = settings
        self._redis = redis_client
        self._storage = storage
        self._vision = vision
        self._search = search
        self._config = config or OrchestratorConfig()
        self._exclude_labels = load_label_set(self._config.exclude_labels_path)
        self._furniture_rules = load_furniture_label_rules(
            settings.FURNITURE_LABEL_RULES_PATH
        )
        self._generic_labels = _parse_label_list(settings.VISION_GENERIC_LABELS)
        self._logger = logger or logging.getLogger("pipeline")
        self._verifier_image_fetch_global_semaphore = asyncio.Semaphore(
            max(int(self._settings.FURNITURE_VERIFIER_IMAGE_FETCH_CONCURRENCY or 1), 1)
        )
        self._simple_pipeline = SimplePipelineRunner(settings, self._logger)
        try:
            self._furniture_verifier: FurnitureVisionVerifier | None = (
                FurnitureVisionVerifier(
                    settings,
                    self._logger,
                    image_fetch_semaphore=self._verifier_image_fetch_global_semaphore,
                )
                if settings.FURNITURE_VERIFIER_ENABLED
                else None
            )
        except Exception as exc:
            self._logger.warning("Furniture verifier init failed: %s", exc)
            self._furniture_verifier = None
        try:
            self._furniture_query_terms: FurnitureQueryTermsService | None = (
                FurnitureQueryTermsService(settings, self._logger)
                if settings.FURNITURE_QUERY_TERMS_ENABLED
                else None
            )
        except Exception as exc:
            self._logger.warning("Furniture query terms init failed: %s", exc)
            self._furniture_query_terms = None
        self._tasks: dict[str, asyncio.Task] = {}
        self._pdf_cache: dict[str, bytes] = {}
        self._render_cache: dict[str, bytes] = {}
        self._global_job_limit = max(
            int(self._settings.WORKER_GLOBAL_ACTIVE_JOBS_LIMIT or 1), 1
        )
        self._global_job_wait_seconds = max(
            float(self._settings.WORKER_GLOBAL_ACTIVE_JOBS_WAIT_SECONDS or 1.0), 0.1
        )
        self._global_job_lease_seconds = max(
            int(self._settings.WORKER_GLOBAL_ACTIVE_JOBS_LEASE_SECONDS or 1), 1
        )
        self._service_costs = {
            "vision": settings.COST_VISION,
            "searchapi": settings.COST_SEARCHAPI,
        }

    async def start_job(
        self,
        chat_id: int,
        photo: bytes,
        text: str,
        style_reference: bytes | None = None,
        seed: int | None = None,
        mode: str = MODE_RENDER_ONLY,
        units_spent: int = 0,
    ) -> str:
        resolved_mode = (mode or MODE_RENDER_ONLY).strip().lower()
        if resolved_mode not in {MODE_RENDER_ONLY, MODE_FURNITURE_SEARCH}:
            resolved_mode = MODE_RENDER_ONLY
        job_id = self._redis.new_job_id(chat_id)
        job = Job(
            job_id=job_id,
            chat_id=chat_id,
            status="queued",
            user_prompt=text,
            mode=resolved_mode,
            units_spent=max(int(units_spent or 0), 0),
        )
        self._redis.store_job(job)
        task = asyncio.create_task(
            self._run_job_with_global_limit(
                job,
                photo,
                text,
                style_reference,
                seed,
                resolved_mode,
            )
        )
        self._tasks[job_id] = task
        return job_id

    async def _run_job_with_global_limit(
        self,
        job: Job,
        photo: bytes,
        text: str,
        style_reference: bytes | None,
        seed: int | None,
        mode: str,
    ) -> None:
        acquired = False
        wait_started = time.perf_counter()
        next_log_at = wait_started
        try:
            while True:
                try:
                    acquired = self._redis.try_acquire_global_job_slot(
                        job.job_id,
                        limit=self._global_job_limit,
                        lease_seconds=self._global_job_lease_seconds,
                    )
                except Exception as exc:
                    # Fail-open to avoid deadlocking the worker on Redis-side issues.
                    self._logger.warning(
                        "global_job_limiter_error job=%s proceeding_without_limit error=%s",
                        job.job_id,
                        exc,
                    )
                    acquired = False
                    break

                if acquired:
                    waited = time.perf_counter() - wait_started
                    if waited >= 0.5:
                        self._logger.info(
                            "global_job_slot_acquired job=%s limit=%s waited=%.2fs active=%s",
                            job.job_id,
                            self._global_job_limit,
                            waited,
                            self._redis.get_global_active_job_count(),
                        )
                    break

                now = time.perf_counter()
                if now >= next_log_at:
                    self._logger.info(
                        "global_job_slot_waiting job=%s limit=%s active=%s waited=%.2fs",
                        job.job_id,
                        self._global_job_limit,
                        self._redis.get_global_active_job_count(),
                        now - wait_started,
                    )
                    next_log_at = now + 10.0
                await asyncio.sleep(self._global_job_wait_seconds)

            queue_wait_seconds = max(time.perf_counter() - wait_started, 0.0)
            if queue_wait_seconds >= 0.5:
                self._logger.info(
                    "global_job_queue_wait_done job=%s waited=%.2fs",
                    job.job_id,
                    queue_wait_seconds,
                )
            await self._run_job(
                job,
                photo,
                text,
                style_reference,
                seed,
                mode,
                queue_wait_seconds=queue_wait_seconds,
            )
        finally:
            if acquired:
                try:
                    self._redis.release_global_job_slot(job.job_id)
                except Exception as exc:
                    self._logger.warning(
                        "global_job_slot_release_failed job=%s error=%s",
                        job.job_id,
                        exc,
                    )
            self._tasks.pop(job.job_id, None)

    async def poll_job(self, job_id: str) -> tuple[str, bytes | None]:
        job = self._redis.get_job(job_id)
        if not job:
            return "unknown", None
        if job_id in self._render_cache:
            return "rendered", self._render_cache.pop(job_id)
        if job.status == "done":
            return "done", self._pdf_cache.get(job_id)
        if job.status == "failed":
            return "failed", None
        return job.status, None

    async def _run_job(
        self,
        job: Job,
        photo: bytes,
        text: str,
        style_reference: bytes | None,
        seed: int | None,
        mode: str,
        queue_wait_seconds: float = 0.0,
    ) -> None:
        start_time = time.perf_counter()
        run_started_unix = time.time()
        job.status = "processing"
        self._redis.store_job(job)
        self._logger.info(
            "Pipeline start job=%s chat_id=%s mode=%s units=%s queue_wait=%.2fs",
            job.job_id,
            job.chat_id,
            mode,
            job.units_spent,
            max(queue_wait_seconds, 0.0),
        )
        debug_payload: dict[str, object] = {
            "job_id": job.job_id,
            "mode": mode,
            "units_spent": job.units_spent,
            "queue_wait_seconds": round(max(queue_wait_seconds, 0.0), 3),
            "queue_wait_ms": int(round(max(queue_wait_seconds, 0.0) * 1000)),
            "queued_at": _to_utc_iso(job.created_at),
            "run_started_at": _unix_to_utc_iso(run_started_unix),
            "style_reference_enabled": bool(style_reference),
            "style_ref_source": "telegram_user_photo" if style_reference else "none",
            "style_ref_used": False,
            "style_ref_status": "requested" if style_reference else "not_requested",
        }
        design_id = None
        error_stage = "start"
        try:
            error_stage = "input_upload"
            style_reference_url: str | None = None
            style_reference_external_url: str | None = None
            input_image_url = await self._upload_input(photo)
            job.input_image_key = input_image_url
            if style_reference:
                style_reference_url = await self._upload_stage(style_reference, ".jpg", "style_refs")
                debug_payload["style_reference_image_url"] = style_reference_url
                debug_payload["style_ref_url"] = _mask_style_ref_url(style_reference_url)
                style_reference_external_url = await self._build_external_media_url(
                    style_reference_url,
                    job_id=job.job_id,
                    label="style_reference_external_url",
                )
                debug_payload["style_reference_external_url_masked"] = (
                    _mask_style_ref_url(style_reference_external_url)
                    if style_reference_external_url
                    else None
                )
            self._logger.info(
                "Pipeline job=%s input_upload_done elapsed=%.2fs",
                job.job_id,
                time.perf_counter() - start_time,
            )
            if seed is not None:
                debug_payload["seed"] = seed
            error_stage = "db_create"
            design_id = await self._create_design_record(
                (job.chat_id if job.chat_id > 0 else None),
                input_image_url,
                text,
                mode=mode,
                units_spent=job.units_spent,
                account_id=job.account_id,
                job_id=(job.job_id if _looks_like_uuid(job.job_id) else None),
                draft_id=(job.draft_id if _looks_like_uuid(job.draft_id) else None),
                style_reference_image_url=style_reference_url,
                style_reference_used=False,
                style_reference_status="requested" if style_reference else "not_requested",
            )
            if design_id:
                debug_payload["design_id"] = str(design_id)

            simple_debug: dict[str, object] = {}
            render_bytes = photo
            prepared_url = None
            render_url = None
            fix_url = None
            final_url = None
            style_reference_url = (
                str(debug_payload.get("style_reference_image_url"))
                if debug_payload.get("style_reference_image_url")
                else None
            )
            if mode != MODE_FURNITURE_SEARCH:
                error_stage = "simple_pipeline"
                try:
                    simple_result = await self._simple_pipeline.run(
                        photo,
                        text,
                        job.job_id,
                        style_reference_bytes=style_reference,
                        input_image_url=input_image_url,
                        style_reference_image_url=style_reference_external_url,
                    )
                except PlannerBlockedError as blocked:
                    simple_debug = blocked.debug
                    style_ref_used, style_ref_source, style_ref_url, style_ref_status = _resolve_style_ref_fields(
                        style_reference_requested=bool(style_reference),
                        style_reference_url=style_reference_url,
                        simple_debug=simple_debug,
                    )
                    debug_payload["style_ref_used"] = style_ref_used
                    debug_payload["style_ref_source"] = style_ref_source
                    debug_payload["style_ref_url"] = style_ref_url
                    debug_payload["style_ref_status"] = style_ref_status
                    debug_payload["simple_pipeline"] = simple_debug
                    debug_payload["planner_block_message"] = blocked.user_message
                    job.status = "done"
                    self._redis.store_job(job)
                    self._pdf_cache[job.job_id] = blocked.user_message.encode("utf-8")
                    await self._store_debug(job.job_id, debug_payload)
                    duration = time.perf_counter() - start_time
                    self._redis.record_metric(job.chat_id, duration, True)
                    await self._update_design_record(
                        design_id=design_id,
                        status="blocked",
                        duration_seconds=int(duration),
                        prepared_image_url=None,
                        render_image_url=None,
                        fix_image_url=None,
                        final_image_url=None,
                        selected_image=None,
                        score_render=None,
                        score_fix=None,
                        providers_json=_build_providers_json(simple_debug),
                        debug_json=debug_payload,
                        metadata_json=_attach_queue_metadata(
                            _build_metadata_json(
                                simple_debug=simple_debug,
                                objects_count=0,
                                object_cards_count=0,
                                products_count=0,
                            ),
                            queue_wait_seconds=queue_wait_seconds,
                            total_elapsed_seconds=queue_wait_seconds + duration,
                            queued_at=job.created_at,
                            run_started_unix=run_started_unix,
                        ),
                        style_reference_image_url=(
                            str(style_reference_url) if style_reference_url else None
                        ),
                        style_reference_used=style_ref_used,
                        style_reference_status=style_ref_status,
                        pipeline_version=self._settings.PIPELINE_VERSION,
                        cost_usd=_compute_total_cost(job, simple_debug),
                        error_stage="planner_blocked",
                        error_message=blocked.user_message,
                    )
                    self._logger.info(
                        "Pipeline job=%s planner_blocked reason=%s style_ref_used=%s style_ref_source=%s style_ref_url=%s style_ref_status=%s elapsed=%.2fs",
                        job.job_id,
                        blocked.block_reason,
                        style_ref_used,
                        style_ref_source,
                        style_ref_url,
                        style_ref_status,
                        time.perf_counter() - start_time,
                        extra={
                            "style_ref_used": style_ref_used,
                            "style_ref_source": style_ref_source,
                            "style_ref_url": style_ref_url,
                            "style_ref_status": style_ref_status,
                        },
                    )
                    return
                render_bytes = simple_result.best_bytes
                simple_debug = simple_result.debug
                style_ref_used, style_ref_source, style_ref_url, style_ref_status = _resolve_style_ref_fields(
                    style_reference_requested=bool(style_reference),
                    style_reference_url=style_reference_url,
                    simple_debug=simple_debug,
                )
                debug_payload["style_ref_used"] = style_ref_used
                debug_payload["style_ref_source"] = style_ref_source
                debug_payload["style_ref_url"] = style_ref_url
                debug_payload["style_ref_status"] = style_ref_status
                debug_payload["degraded"] = bool(simple_debug.get("degraded"))
                debug_payload["degraded_reasons"] = simple_debug.get("degraded_reasons") or []
                debug_payload["simple_pipeline"] = simple_debug
                job.render_prompt = (
                    str(simple_debug.get("render_prompt", "")).strip() or None
                )
                image_cost_total = _extract_image_cost_total(simple_debug)
                if image_cost_total is not None and image_cost_total > 0:
                    self._redis.record_cost("gpt_image", image_cost_total)
                    job.costs["gpt_image"] = job.costs.get("gpt_image", 0.0) + image_cost_total
                    self._logger.info(
                        "Pipeline job=%s gpt_image_cost_usd=%.6f source=%s",
                        job.job_id,
                        image_cost_total,
                        simple_debug.get("image_cost_sources"),
                    )
                elif (
                    simple_debug.get("render_provider") == "gpt"
                    or simple_debug.get("rerender_provider") == "gpt"
                    or simple_debug.get("fix_provider") == "gpt"
                ):
                    self._logger.warning(
                        "Pipeline job=%s gpt_image_cost_missing render_usd=%s rerender_usd=%s sources=%s pricing=%s",
                        job.job_id,
                        simple_debug.get("render_cost_usd"),
                        simple_debug.get("rerender_cost_usd")
                        if simple_debug.get("rerender_cost_usd") is not None
                        else simple_debug.get("fix_cost_usd"),
                        simple_debug.get("image_cost_sources"),
                        simple_debug.get("image_pricing_config"),
                    )
                self._logger.info(
                    "Pipeline job=%s simple_pipeline_done elapsed=%.2fs",
                    job.job_id,
                    time.perf_counter() - start_time,
                )

                error_stage = "upload_outputs"
                prepared_url = await self._upload_stage(simple_result.prepared_png, ".png", "prepared")
                render_suffix = _image_suffix_for_bytes(simple_result.render_bytes)
                render_url = await self._upload_stage(simple_result.render_bytes, render_suffix, "render")
                rerender_bytes = (
                    getattr(simple_result, "rerender_bytes", None) or simple_result.fix_bytes
                )
                if rerender_bytes:
                    fix_suffix = _image_suffix_for_bytes(rerender_bytes)
                    fix_url = await self._upload_stage(rerender_bytes, fix_suffix, "rerender")
                final_suffix = _image_suffix_for_bytes(render_bytes)
                final_url = await self._upload_stage(render_bytes, final_suffix, "final")
                debug_payload["prepared_image_url"] = prepared_url
                debug_payload["render_image_url"] = render_url
                debug_payload["rerender_image_url"] = fix_url
                debug_payload["final_image_url"] = final_url
                job.render_image_key = final_url
            else:
                self._logger.info(
                    "Pipeline job=%s mode=furniture_search skip_simple_pipeline",
                    job.job_id,
                )
            objects: list[VisionObject] = []
            products: list[ProductResult] = []
            object_cards: list[dict] = []
            numbered_boxes: list[dict] = []

            if mode == MODE_RENDER_ONLY:
                self._render_cache[job.job_id] = render_bytes
                self._pdf_cache[job.job_id] = b""
                self._logger.info(
                    "Pipeline job=%s render_only_done elapsed=%.2fs",
                    job.job_id,
                    time.perf_counter() - start_time,
                )
            elif mode == MODE_FURNITURE_SEARCH:
                self._logger.info(
                    "Pipeline job=%s furniture_vision_start elapsed=%.2fs",
                    job.job_id,
                    time.perf_counter() - start_time,
                )
                error_stage = "vision"
                vision_payload = await self._timed_call(
                    job, job.chat_id, "vision", self._vision.detect_objects, photo
                )
                debug_payload["vision"] = vision_payload
                objects = parse_vision(
                    vision_payload,
                    exclude_labels=self._exclude_labels,
                    min_score=self._config.min_score,
                    min_area=self._config.min_area,
                    max_objects=self._config.max_objects,
                    prefetch_n=self._config.prefetch_n,
                    iou_threshold=self._config.iou_threshold,
                    containment_threshold=self._config.containment_threshold,
                    max_per_label=self._config.max_per_label,
                    generic_labels=self._generic_labels,
                    generic_iou_threshold=self._settings.VISION_GENERIC_IOU_THRESHOLD,
                    generic_containment_threshold=self._settings.VISION_GENERIC_CONTAINMENT_THRESHOLD,
                    global_iou_threshold=self._settings.VISION_DUPLICATE_IOU_THRESHOLD,
                    global_containment_threshold=self._settings.VISION_DUPLICATE_CONTAINMENT_THRESHOLD,
                )
                job.vision_objects = objects
                self._logger.info(
                    "Pipeline job=%s furniture_vision_done objects=%s elapsed=%.2fs",
                    job.job_id,
                    len(objects),
                    time.perf_counter() - start_time,
                )

                error_stage = "search"
                products, object_cards, numbered_boxes = await self._process_objects(
                    job,
                    job.chat_id,
                    photo,
                    objects,
                    only_with_links=True,
                )
                job.product_results = products
                debug_payload["object_cards"] = object_cards
                debug_payload["products_count"] = len(products)
                overlay_image = apply_numbered_overlay(
                    photo,
                    numbered_boxes,
                    output_format="JPEG",
                )
                error_stage = "upload_outputs"
                final_url = await self._upload_stage(overlay_image, ".jpg", "final")
                debug_payload["final_image_url"] = final_url
                job.render_image_key = final_url
                self._render_cache[job.job_id] = overlay_image
                summary_text = _format_furniture_summary(object_cards)
                self._pdf_cache[job.job_id] = summary_text.encode("utf-8")
                debug_payload["furniture_summary"] = summary_text
                self._logger.info(
                    "Pipeline job=%s furniture_done cards=%s links=%s elapsed=%.2fs",
                    job.job_id,
                    len(object_cards),
                    len(products),
                    time.perf_counter() - start_time,
                )
            job.status = "done"
            self._redis.store_job(job)
            await self._store_debug(job.job_id, debug_payload)
            duration = time.perf_counter() - start_time
            self._redis.record_metric(job.chat_id, duration, True)
            error_stage = "db_update"
            await self._update_design_record(
                design_id=design_id,
                status=_derive_design_success_status(mode, simple_debug),
                duration_seconds=int(duration),
                prepared_image_url=prepared_url,
                render_image_url=render_url,
                fix_image_url=fix_url,
                final_image_url=final_url,
                selected_image=(
                    "input"
                    if mode == MODE_FURNITURE_SEARCH
                    else str(simple_debug.get("best_label") or "A")
                ),
                score_render=_compute_score(simple_debug.get("render_validation", {}).get("scores")),
                score_fix=_compute_score(
                    (
                        simple_debug.get("rerender_validation")
                        or simple_debug.get("fix_validation")
                        or {}
                    ).get("scores")
                ),
                providers_json=_build_providers_json(simple_debug),
                debug_json=debug_payload,
                metadata_json=_attach_queue_metadata(
                    _build_metadata_json(
                        simple_debug=simple_debug,
                        objects_count=len(objects),
                        object_cards_count=len(object_cards),
                        products_count=len(products),
                    ),
                    queue_wait_seconds=queue_wait_seconds,
                    total_elapsed_seconds=queue_wait_seconds + duration,
                    queued_at=job.created_at,
                    run_started_unix=run_started_unix,
                ),
                style_reference_image_url=(
                    str(style_reference_url) if style_reference_url else None
                ),
                style_reference_used=bool(debug_payload.get("style_ref_used")),
                style_reference_status=(
                    str(debug_payload.get("style_ref_status"))
                    if debug_payload.get("style_ref_status") is not None
                    else None
                ),
                pipeline_version=self._settings.PIPELINE_VERSION,
                cost_usd=_compute_total_cost(job, simple_debug),
                error_stage=None,
                error_message=None,
            )
            self._logger.info(
                "Pipeline done job=%s mode=%s degraded=%s degraded_reasons=%s style_ref_used=%s style_ref_source=%s style_ref_url=%s style_ref_status=%s elapsed=%.2fs queue_wait=%.2fs total=%.2fs",
                job.job_id,
                mode,
                bool(debug_payload.get("degraded")),
                debug_payload.get("degraded_reasons"),
                bool(debug_payload.get("style_ref_used")),
                debug_payload.get("style_ref_source"),
                debug_payload.get("style_ref_url"),
                debug_payload.get("style_ref_status"),
                time.perf_counter() - start_time,
                max(queue_wait_seconds, 0.0),
                max(queue_wait_seconds, 0.0) + (time.perf_counter() - start_time),
                extra={
                    "degraded": bool(debug_payload.get("degraded")),
                    "degraded_reasons": debug_payload.get("degraded_reasons"),
                    "style_ref_used": bool(debug_payload.get("style_ref_used")),
                    "style_ref_source": debug_payload.get("style_ref_source"),
                    "style_ref_url": debug_payload.get("style_ref_url"),
                    "style_ref_status": debug_payload.get("style_ref_status"),
                },
            )
        except Exception as exc:
            if isinstance(exc, SimplePipelineError):
                debug_payload["simple_pipeline"] = exc.debug
                error_stage = exc.stage
            simple_debug = debug_payload.get("simple_pipeline") or {}
            style_ref_used, style_ref_source, style_ref_url, style_ref_status = _resolve_style_ref_fields(
                style_reference_requested=bool(style_reference),
                style_reference_url=(
                    str(debug_payload.get("style_reference_image_url"))
                    if debug_payload.get("style_reference_image_url")
                    else None
                ),
                simple_debug=simple_debug if isinstance(simple_debug, dict) else {},
            )
            debug_payload["style_ref_used"] = style_ref_used
            debug_payload["style_ref_source"] = style_ref_source
            debug_payload["style_ref_url"] = style_ref_url
            debug_payload["style_ref_status"] = style_ref_status
            job.status = "failed"
            job.debug["error"] = str(exc)
            self._redis.store_job(job)
            duration = time.perf_counter() - start_time
            self._redis.record_metric(job.chat_id, duration, False)
            await self._store_debug(job.job_id, debug_payload, error=exc)
            await self._update_design_record(
                design_id=design_id,
                status="error",
                duration_seconds=int(duration),
                prepared_image_url=debug_payload.get("prepared_image_url"),
                render_image_url=debug_payload.get("render_image_url"),
                fix_image_url=debug_payload.get("rerender_image_url") or debug_payload.get("fix_image_url"),
                final_image_url=debug_payload.get("final_image_url"),
                selected_image=(
                    "input"
                    if mode == MODE_FURNITURE_SEARCH
                    else (str(simple_debug.get("best_label") or "") or None)
                ),
                score_render=_compute_score(
                    (simple_debug.get("render_validation") or {}).get("scores")
                ),
                score_fix=_compute_score(
                    (
                        simple_debug.get("rerender_validation")
                        or simple_debug.get("fix_validation")
                        or {}
                    ).get("scores")
                ),
                providers_json=_build_providers_json(simple_debug),
                debug_json=debug_payload,
                metadata_json=_attach_queue_metadata(
                    _build_metadata_json(
                        simple_debug=simple_debug,
                        objects_count=len(job.vision_objects or []),
                        object_cards_count=None,
                        products_count=len(job.product_results or []),
                    ),
                    queue_wait_seconds=queue_wait_seconds,
                    total_elapsed_seconds=queue_wait_seconds + duration,
                    queued_at=job.created_at,
                    run_started_unix=run_started_unix,
                ),
                style_reference_image_url=(
                    str(debug_payload.get("style_reference_image_url"))
                    if debug_payload.get("style_reference_image_url")
                    else None
                ),
                style_reference_used=style_ref_used,
                style_reference_status=style_ref_status,
                pipeline_version=self._settings.PIPELINE_VERSION,
                cost_usd=_compute_total_cost(job, simple_debug),
                error_stage=error_stage,
                error_message=str(exc),
            )
            self._logger.exception(
                "Pipeline failed for job %s style_ref_used=%s style_ref_source=%s style_ref_url=%s style_ref_status=%s",
                job.job_id,
                style_ref_used,
                style_ref_source,
                style_ref_url,
                style_ref_status,
                extra={
                    "style_ref_used": style_ref_used,
                    "style_ref_source": style_ref_source,
                    "style_ref_url": style_ref_url,
                    "style_ref_status": style_ref_status,
                },
            )

    async def _upload_render(self, render_bytes: bytes, suffix: str) -> str:
        return await asyncio.to_thread(self._storage.upload_bytes, render_bytes, suffix)

    async def _upload_stage(
        self, data: bytes, suffix: str, prefix: str
    ) -> str:
        return await asyncio.to_thread(self._storage.upload_bytes, data, suffix, prefix)

    async def _build_external_media_url(
        self,
        url: str | None,
        *,
        job_id: str,
        label: str,
    ) -> str | None:
        if not url:
            return None
        key = self._storage.extract_storage_key(url)
        if not key:
            return url
        try:
            return await asyncio.to_thread(
                self._storage.get_signed_object_url,
                key,
                max(int(self._settings.S3_PRESIGN_EXPIRES or 3600), 300),
            )
        except Exception as exc:
            self._logger.warning(
                "Pipeline job=%s %s_sign_failed key=%s error=%s",
                job_id,
                label,
                key,
                exc,
            )
            return None

    async def _upload_input(self, photo: bytes) -> str:
        if self._settings.S3_PRESIGN_INPUTS:
            return await asyncio.to_thread(
                self._storage.upload_bytes_presigned,
                photo,
                ".jpg",
                "inputs",
                self._settings.S3_PRESIGN_EXPIRES,
            )
        return await asyncio.to_thread(self._storage.upload_bytes, photo, ".jpg", "inputs")

    async def _create_design_record(
        self,
        user_id: int | None,
        original_image_url: str,
        user_request: str,
        mode: str = MODE_RENDER_ONLY,
        units_spent: int | None = None,
        account_id: str | None = None,
        job_id: str | None = None,
        draft_id: str | None = None,
        style_reference_image_url: str | None = None,
        style_reference_used: bool | None = None,
        style_reference_status: str | None = None,
    ):
        def _create():
            with get_db_session() as session:
                repo = DesignRepository(session)
                design = repo.create_design(
                    user_id=user_id,
                    original_image_url=original_image_url,
                    user_request=user_request,
                    status="processing",
                    mode=mode,
                    units_spent=units_spent,
                    account_id=(UUID(account_id) if account_id else None),
                    job_id=(UUID(job_id) if job_id else None),
                    draft_id=(UUID(draft_id) if draft_id else None),
                    style_reference_image_url=style_reference_image_url,
                    style_reference_used=style_reference_used,
                    style_reference_status=style_reference_status,
                )
                return design.id

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:
            self._logger.warning("DB create failed: %s", exc)
            return None

    async def _update_design_record(
        self,
        design_id,
        status: str,
        duration_seconds: int,
        prepared_image_url: str | None,
        render_image_url: str | None,
        fix_image_url: str | None,
        final_image_url: str | None,
        selected_image: str | None,
        score_render: int | None,
        score_fix: int | None,
        providers_json: dict | None,
        debug_json: dict,
        metadata_json: dict | None,
        style_reference_image_url: str | None,
        style_reference_used: bool | None,
        style_reference_status: str | None,
        pipeline_version: str | None,
        cost_usd: float | None,
        error_stage: str | None,
        error_message: str | None,
    ) -> None:
        if not design_id:
            return

        def _update():
            with get_db_session() as session:
                repo = DesignRepository(session)
                repo.set_result(
                    design_id=design_id,
                    final_image_url=final_image_url,
                    status=status,
                    duration_seconds=duration_seconds,
                    cost_usd=cost_usd,
                    error_message=error_message,
                    selected_image=selected_image,
                    score_render=score_render,
                    score_fix=score_fix,
                    providers_json=providers_json,
                    debug_json=debug_json,
                    metadata_json=metadata_json,
                    prepared_image_url=prepared_image_url,
                    render_image_url=render_image_url,
                    fix_image_url=fix_image_url,
                    style_reference_image_url=style_reference_image_url,
                    style_reference_used=style_reference_used,
                    style_reference_status=style_reference_status,
                    error_stage=error_stage,
                    pipeline_version=pipeline_version,
                )

        try:
            await asyncio.to_thread(_update)
        except Exception as exc:
            self._logger.warning("DB update failed: %s", exc)

    async def _process_objects(
        self,
        job: Job,
        chat_id: int,
        render_bytes: bytes,
        objects: list[VisionObject],
        only_with_links: bool = False,
    ) -> tuple[list[ProductResult], list[dict], list[dict]]:
        if not objects:
            return [], [], []

        crop_format = (self._settings.CROP_IMAGE_FORMAT or "JPEG").upper().strip()
        mask_shrink = self._settings.CROP_MASK_SHRINK_RATIO
        mask_transparent = self._settings.CROP_MASK_TRANSPARENT
        crops = await asyncio.to_thread(
            batch_crop,
            render_bytes,
            objects,
            image_format=crop_format,
            mask_shrink_ratio=mask_shrink,
            mask_transparent=mask_transparent,
        )
        results: list[ProductResult] = []
        cards: list[dict] = []
        numbered_boxes: list[dict] = []
        marketplaces = [
            ("ozon", "ozon.ru"),
            ("yandex_market", "market.yandex.ru"),
            ("wildberries", "wildberries.ru"),
        ]
        crop_indexes = [
            (index, item)
            for index, item in enumerate(crops, start=1)
            if item["object"].bounding_box
        ]
        crop_concurrency = max(
            int(self._settings.FURNITURE_SEARCH_CROP_CONCURRENCY or 1), 1
        )
        market_concurrency = min(
            max(int(self._settings.FURNITURE_SEARCH_MARKET_CONCURRENCY or 1), 1),
            len(marketplaces),
        )
        self._logger.info(
            "Pipeline job=%s furniture_search_parallel crop_concurrency=%s market_concurrency=%s",
            job.job_id,
            crop_concurrency,
            market_concurrency,
        )
        llm_by_crop: dict[str, object] = {}
        llm_batch_debug: dict[str, object] = {
            "enabled": bool(self._furniture_query_terms is not None),
            "used": False,
        }
        if self._furniture_query_terms is not None and crop_indexes:
            llm_inputs = [
                QueryTermsCropInput(
                    crop_id=str(index),
                    vision_label=str(item["object"].label or ""),
                    image_bytes=item["bytes"],
                )
                for index, item in crop_indexes
            ]
            try:
                llm_result = await self._furniture_query_terms.infer(crops=llm_inputs)
            except Exception as exc:
                llm_result = None
                self._logger.warning(
                    "Furniture query terms failed for job=%s: %s",
                    job.job_id,
                    exc,
                )
            if llm_result is not None:
                llm_by_crop = llm_result.results_by_crop
                llm_batch_debug.update(
                    {
                        "used": True,
                        "provider": llm_result.provider,
                        "model": llm_result.model,
                        "usage": llm_result.usage,
                        "cost_usd": llm_result.cost_usd,
                        "cost_source": llm_result.cost_source,
                    }
                )
                if isinstance(llm_result.cost_usd, (int, float)) and llm_result.cost_usd > 0:
                    self._redis.record_cost("furniture_query_terms", llm_result.cost_usd)
                    job.costs["furniture_query_terms"] = (
                        job.costs.get("furniture_query_terms", 0.0)
                        + float(llm_result.cost_usd)
                    )
                    self._logger.info(
                        "Pipeline job=%s furniture_query_terms_cost_usd=%.6f source=%s",
                        job.job_id,
                        float(llm_result.cost_usd),
                        llm_result.cost_source,
                    )
            else:
                llm_batch_debug["fallback_reason"] = "llm_a_failed_or_invalid_json"

        async def _process_single_crop(
            crop_index: int, item: dict
        ) -> dict[str, object] | None:
            obj = item["object"]
            llm_item = llm_by_crop.get(str(crop_index))
            rule = self._furniture_rules.resolve_type_rule(obj.label)
            display_name_ru = (
                str(getattr(llm_item, "display_name_ru", "")).strip()
                if llm_item is not None
                else ""
            )
            if not display_name_ru:
                display_name_ru = obj.label
            if is_delete_marker(display_name_ru):
                self._logger.info(
                    "Pipeline job=%s furniture_duplicate_skipped crop=%s label=%s",
                    job.job_id,
                    crop_index,
                    obj.label,
                )
                return {
                    "results": [],
                    "skip_reason": "duplicate_crop",
                    "crop_index": crop_index,
                }
            llm_terms = list(getattr(llm_item, "query_terms", ()) or ())
            if llm_item is None:
                query_terms = list(rule.query_terms)
            else:
                query_terms = llm_terms
            query_terms_source = (
                "llm_a"
                if llm_terms
                else ("rule_fallback" if llm_item is None else "llm_a_empty")
            )
            if self._settings.S3_PRESIGN_INPUTS:
                crop_url = await asyncio.to_thread(
                    self._storage.upload_bytes_presigned,
                    item["bytes"],
                    ".jpg",
                    None,
                    self._settings.S3_PRESIGN_EXPIRES,
                )
            else:
                crop_url = await asyncio.to_thread(
                    self._storage.upload_bytes, item["bytes"], ".jpg"
                )
            obj.crop_key = crop_url
            links_by_market: dict[str, list[str]] = {}
            card_debug: dict[str, object] = {
                "crop_index": crop_index,
                "vision_label": obj.label,
                "display_name_ru": display_name_ru,
                "expected_type": rule.type_name,
                "search_enabled": rule.search_enabled,
                "query_terms": list(query_terms),
                "query_terms_source": query_terms_source,
                "llm_a_batch": dict(llm_batch_debug),
            }

            ranked_by_market: dict[str, list[SearchCandidate]] = {}
            market_debug: dict[str, dict[str, object]] = {}
            if rule.search_enabled:

                async def _search_market(
                    marketplace: str,
                    domain: str,
                ) -> tuple[str, list[SearchCandidate], dict[str, object]]:
                    query = _build_search_query(domain=domain, query_terms=query_terms)
                    context: dict[str, object] = {
                        "crop_index": crop_index,
                        "vision_label": obj.label,
                        "query": query,
                        "search_type": self._settings.SEARCHAPI_SEARCH_TYPE,
                        "hl": self._settings.SEARCHAPI_HL,
                        "country": self._settings.SEARCHAPI_COUNTRY,
                        "device": self._settings.SEARCHAPI_DEVICE,
                        "candidate_source": None,
                        "raw_visual_matches": 0,
                        "kept_after_domain_filter": 0,
                        "image_url_found": 0,
                        "raw_candidates": 0,
                        "kept_candidates": 0,
                        "top5_candidates": 0,
                    }
                    try:

                        async def _search_checked() -> dict:
                            payload = await self._search.search(
                                crop_url,
                                query,
                                marketplace=marketplace,
                                search_type=self._settings.SEARCHAPI_SEARCH_TYPE,
                                hl=self._settings.SEARCHAPI_HL,
                                country=self._settings.SEARCHAPI_COUNTRY,
                                device=self._settings.SEARCHAPI_DEVICE,
                            )
                            error_message = searchapi_error_message(payload)
                            if error_message:
                                raise RuntimeError(error_message)
                            return payload

                        payload = await self._timed_call(
                            job,
                            chat_id,
                            f"searchapi crop={crop_index} label={obj.label} market={marketplace}",
                            _search_checked,
                            retry_attempts=self._settings.SEARCHAPI_RETRY_ATTEMPTS,
                            retry_base_delay=self._settings.SEARCHAPI_RETRY_BASE_DELAY,
                            retry_max_delay=self._settings.SEARCHAPI_RETRY_MAX_DELAY,
                        )
                    except Exception as exc:
                        error_type = type(exc).__name__
                        error_text = _sanitize_error_text(str(exc).strip() or repr(exc))
                        self._logger.warning(
                            (
                                "User %s job=%s: searchapi failed crop=%s label=%s market=%s "
                                "error_type=%s error=%s"
                            ),
                            chat_id,
                            job.job_id,
                            crop_index,
                            obj.label,
                            marketplace,
                            error_type,
                            error_text,
                        )
                        context["error"] = "search_failed"
                        context["error_type"] = error_type
                        context["error_message"] = error_text[:300]
                        return marketplace, [], context

                    context["candidate_source"] = searchapi_candidate_source(payload)
                    context["raw_visual_matches"] = searchapi_visual_matches_count(payload)
                    candidate_samples = searchapi_candidate_samples(payload, limit=3)
                    if candidate_samples:
                        context["raw_candidate_samples"] = candidate_samples

                    raw_candidates = extract_searchapi_candidates(
                        payload=payload,
                        label=obj.label,
                        marketplace=marketplace,
                        limit=self._settings.FURNITURE_SEARCH_CANDIDATE_SCAN_LIMIT,
                    )
                    context["kept_after_domain_filter"] = len(raw_candidates)
                    context["image_url_found"] = len(
                        [candidate for candidate in raw_candidates if candidate.image_url]
                    )
                    ranked_candidates = rank_searchapi_candidates(
                        candidates=raw_candidates,
                        include_tokens=list(rule.include_tokens),
                        exclude_tokens=list(rule.exclude_tokens),
                        limit=None,
                    )
                    context["raw_candidates"] = len(raw_candidates)
                    context["kept_candidates"] = len(ranked_candidates)
                    context["top5_candidates"] = min(len(ranked_candidates), 5)
                    context["top_token_ranked"] = [
                        {
                            "url": candidate.url,
                            "title": candidate.title,
                            "position": candidate.position,
                            "token_score": candidate.token_score,
                            "include_match": candidate.include_match,
                        }
                        for candidate in ranked_candidates[:5]
                    ]
                    return marketplace, ranked_candidates, context

                if market_concurrency == 1:
                    for marketplace, domain in marketplaces:
                        (
                            marketplace,
                            ranked_candidates,
                            context,
                        ) = await _search_market(marketplace, domain)
                        ranked_by_market[marketplace] = ranked_candidates
                        market_debug[marketplace] = context
                else:
                    market_semaphore = asyncio.Semaphore(market_concurrency)

                    async def _run_market(
                        marketplace: str, domain: str
                    ) -> tuple[str, list[SearchCandidate], dict[str, object]]:
                        async with market_semaphore:
                            return await _search_market(marketplace, domain)

                    market_outputs = await asyncio.gather(
                        *[
                            asyncio.create_task(_run_market(marketplace, domain))
                            for marketplace, domain in marketplaces
                        ]
                    )
                    for marketplace, ranked_candidates, context in market_outputs:
                        ranked_by_market[marketplace] = ranked_candidates
                        market_debug[marketplace] = context
            else:
                for marketplace, _ in marketplaces:
                    ranked_by_market[marketplace] = []
                    market_debug[marketplace] = {"search_skipped": True}

            verifier_debug: dict[str, object] = {
                "enabled": bool(self._furniture_verifier is not None),
                "used": False,
                "fallback_to_token_rank": True,
                "crop_index": crop_index,
                "vision_label": obj.label,
            }
            selected_by_market: dict[str, list[SearchCandidate]] = {}
            candidate_index: dict[int, SearchCandidate] = {}
            candidate_market: dict[int, str] = {}
            verifier_candidates: dict[str, list[VerifierCandidate]] = {}
            next_candidate_id = 1
            for marketplace, _ in marketplaces:
                selected = ranked_by_market.get(marketplace, [])[
                    : self._settings.FURNITURE_VERIFIER_TOP_N_PER_MARKET
                ]
                market_candidates: list[VerifierCandidate] = []
                for rank_index, candidate in enumerate(selected, start=1):
                    candidate_id = next_candidate_id
                    next_candidate_id += 1
                    candidate_index[candidate_id] = candidate
                    candidate_market[candidate_id] = marketplace
                    market_candidates.append(
                        VerifierCandidate(
                            candidate_id=candidate_id,
                            marketplace=marketplace,
                            title=candidate.title,
                            url=candidate.url,
                            image_url=candidate.image_url,
                            token_score=candidate.token_score,
                            token_rank=rank_index,
                        )
                    )
                verifier_candidates[marketplace] = market_candidates

            verifier_top_ids: dict[str, list[int]] = {}
            if self._furniture_verifier is not None and any(verifier_candidates.values()):
                self._logger.info(
                    "Pipeline job=%s furniture_verifier_start crop=%s label=%s",
                    job.job_id,
                    crop_index,
                    obj.label,
                )
                try:
                    verifier_result, verifier_info = await self._furniture_verifier.verify_with_debug(
                        crop_bytes=item["bytes"],
                        crop_id=f"{job.job_id}:{obj.label}:{crop_index}",
                        expected_type=rule.type_name,
                        candidates_by_market=verifier_candidates,
                    )
                except Exception as exc:
                    verifier_result = None
                    verifier_info = None
                    self._logger.warning(
                        "Furniture verifier failed for job=%s crop=%s label=%s: %s",
                        job.job_id,
                        crop_index,
                        obj.label,
                        exc,
                    )
                    verifier_debug["fallback_reason"] = "llm_b_exception"
                if verifier_info is not None:
                    verifier_debug["prepared_candidates_total"] = (
                        verifier_info.prepared_candidates_total
                    )
                    verifier_debug["prepared_candidates_by_market"] = (
                        verifier_info.prepared_candidates_by_market
                    )
                    verifier_debug["input_candidates_total"] = (
                        verifier_info.input_candidates_total
                    )
                    verifier_debug["input_candidates_with_image_url"] = (
                        verifier_info.input_candidates_with_image_url
                    )
                    verifier_debug["input_candidates_with_image_url_by_market"] = (
                        verifier_info.input_candidates_with_image_url_by_market or {}
                    )
                    verifier_debug["download_success_total"] = (
                        verifier_info.download_success_total
                    )
                    verifier_debug["download_success_by_market"] = (
                        verifier_info.download_success_by_market or {}
                    )
                    verifier_debug["download_fail_reason_counts"] = (
                        verifier_info.download_fail_reason_counts or {}
                    )
                    verifier_debug["download_fail_reason_counts_by_market"] = (
                        verifier_info.download_fail_reason_counts_by_market or {}
                    )
                    verifier_debug["model_attempts"] = verifier_info.model_attempts
                    if verifier_info.response_preview:
                        verifier_debug["response_preview"] = verifier_info.response_preview
                if verifier_result is not None:
                    verifier_debug["used"] = True
                    verifier_debug["fallback_to_token_rank"] = False
                    verifier_top_ids = verifier_result.top_ids_by_market
                    verifier_debug["top_ids_by_market"] = verifier_result.top_ids_by_market
                    verifier_debug["scores"] = verifier_result.score_by_id
                    verifier_debug["usage"] = verifier_result.usage
                    verifier_debug["cost_usd"] = verifier_result.cost_usd
                    verifier_debug["cost_source"] = verifier_result.cost_source
                    verifier_debug["raw"] = verifier_result.raw
                    if isinstance(verifier_result.cost_usd, (int, float)) and verifier_result.cost_usd > 0:
                        self._redis.record_cost("furniture_verifier", verifier_result.cost_usd)
                        job.costs["furniture_verifier"] = (
                            job.costs.get("furniture_verifier", 0.0)
                            + float(verifier_result.cost_usd)
                        )
                    self._logger.info(
                        "Pipeline job=%s furniture_verifier_done crop=%s label=%s cost_usd=%s source=%s",
                        job.job_id,
                        crop_index,
                        obj.label,
                        verifier_result.cost_usd,
                        verifier_result.cost_source,
                    )
                else:
                    raw_reason = (
                        verifier_info.failure_reason
                        if verifier_info is not None
                        else None
                    )
                    reason_map = {
                        "no_candidate_images": "llm_b_no_candidate_images",
                        "request_failed": "llm_b_request_failed",
                        "invalid_json": "llm_b_invalid_json",
                    }
                    verifier_debug["fallback_reason"] = reason_map.get(
                        str(raw_reason or "").strip(),
                        "llm_b_failed_or_invalid_json",
                    )
                    if verifier_debug["fallback_reason"] == "llm_b_no_candidate_images":
                        self._logger.warning(
                            (
                                "Pipeline job=%s verifier_no_candidate_images crop=%s label=%s "
                                "input_total=%s with_image=%s download_success=%s fail_reasons=%s"
                            ),
                            job.job_id,
                            crop_index,
                            obj.label,
                            verifier_debug.get("input_candidates_total"),
                            verifier_debug.get("input_candidates_with_image_url"),
                            verifier_debug.get("download_success_total"),
                            verifier_debug.get("download_fail_reason_counts"),
                        )

            for marketplace, _ in marketplaces:
                selected_candidates: list[SearchCandidate] = []
                ids = verifier_top_ids.get(marketplace, [])
                if ids:
                    for candidate_id in ids[: self._settings.FURNITURE_VERIFIER_TOP_N_PER_MARKET]:
                        candidate = candidate_index.get(candidate_id)
                        if candidate is not None:
                            selected_candidates.append(candidate)
                if not selected_candidates:
                    selected_candidates = ranked_by_market.get(marketplace, [])[
                        : self._settings.FURNITURE_VERIFIER_TOP_N_PER_MARKET
                    ]
                selected_by_market[marketplace] = selected_candidates

            scored_by_market: dict[str, list[tuple[SearchCandidate, float | None]]] = {}
            verifier_scores = (
                verifier_debug.get("scores")
                if isinstance(verifier_debug.get("scores"), dict)
                else {}
            )
            if verifier_debug.get("used"):
                scores_int = {
                    int(candidate_id): int(score)
                    for candidate_id, score in verifier_scores.items()
                    if isinstance(candidate_id, (int, str))
                    and str(candidate_id).isdigit()
                    and isinstance(score, (int, float))
                }
                for marketplace, candidates in selected_by_market.items():
                    market_scored: list[tuple[SearchCandidate, float | None]] = []
                    for candidate_id, candidate in candidate_index.items():
                        if candidate_market.get(candidate_id) != marketplace:
                            continue
                        score = scores_int.get(candidate_id)
                        if candidate in candidates:
                            market_scored.append(
                                (candidate, float(score) if score is not None else None)
                            )
                    market_scored.sort(
                        key=lambda item: (
                            -1.0 if item[1] is None else -float(item[1]),
                            item[0].position,
                        )
                    )
                    scored_by_market[marketplace] = market_scored
            else:
                for marketplace, candidates in selected_by_market.items():
                    scored_by_market[marketplace] = [
                        (candidate, _token_rank_fallback_score(candidate))
                        for candidate in candidates
                    ]

            final_scored_links = _select_global_top_links(
                scored_by_market=scored_by_market,
                market_order=[market for market, _ in marketplaces],
                limit=max(int(self._settings.FURNITURE_SEARCH_GLOBAL_TOP_K or 5), 1),
                reserve_requires_score=bool(verifier_debug.get("used")),
            )
            verifier_debug["global_top"] = [
                {
                    "marketplace": marketplace,
                    "url": candidate.url,
                    "title": candidate.title,
                    "image_url": candidate.image_url,
                    "match_score": score,
                }
                for marketplace, candidate, score in final_scored_links
            ]

            links_ranked: list[dict[str, object]] = []
            local_results: list[ProductResult] = []
            for marketplace, _ in marketplaces:
                candidates = [
                    candidate
                    for market, candidate, _ in final_scored_links
                    if market == marketplace
                ]
                links_by_market[marketplace] = [candidate.url for candidate in candidates]
            for marketplace, candidate, score in final_scored_links:
                links_ranked.append(
                    {
                        "marketplace": marketplace,
                        "url": candidate.url,
                        "title": candidate.title,
                        "image_url": candidate.image_url,
                        "match_score": score,
                    }
                )
                local_results.append(
                    ProductResult(
                        label=display_name_ru,
                        url=candidate.url,
                        source=marketplace,
                    )
                )
            if not final_scored_links:
                for marketplace, _ in marketplaces:
                    candidates = selected_by_market.get(marketplace, [])[
                        : self._settings.FURNITURE_SEARCH_PER_MARKET_LIMIT
                    ]
                    links_by_market[marketplace] = [candidate.url for candidate in candidates]
                    for candidate in candidates:
                        links_ranked.append(
                            {
                                "marketplace": marketplace,
                                "url": candidate.url,
                                "title": candidate.title,
                                "image_url": candidate.image_url,
                                "match_score": None,
                            }
                        )
                        local_results.append(
                            ProductResult(
                                label=display_name_ru,
                                url=candidate.url,
                                source=marketplace,
                            )
                        )

            has_links = any(links_by_market.get(market) for market, _ in marketplaces)
            if only_with_links and not has_links:
                return None
            xs = [vertex.x for vertex in obj.bounding_box]
            ys = [vertex.y for vertex in obj.bounding_box]
            if not xs or not ys:
                return None
            x_min = min(xs)
            x_max = max(xs)
            y_min = min(ys)
            y_max = max(ys)
            return {
                "crop_index": crop_index,
                "results": local_results,
                "overlay_box": {
                    "x1": x_min,
                    "y1": y_min,
                    "x2": x_max,
                    "y2": y_max,
                    "label": display_name_ru,
                },
                "card": {
                    "label": display_name_ru,
                    "vision_label": obj.label,
                    "crop_url": crop_url,
                    "links": links_by_market,
                    "ranked_links": links_ranked,
                    "debug": {
                        "rule": card_debug,
                        "markets": market_debug,
                        "verifier": verifier_debug,
                    },
                },
            }

        def _append_crop_output(output: dict[str, object] | None) -> None:
            if not isinstance(output, dict):
                return
            local_results = output.get("results")
            if isinstance(local_results, list):
                results.extend(local_results)
            overlay_box = (
                output.get("overlay_box") if isinstance(output.get("overlay_box"), dict) else None
            )
            card = output.get("card") if isinstance(output.get("card"), dict) else None
            if not overlay_box or not card:
                return
            marker_index = len(numbered_boxes) + 1
            numbered_boxes.append({"index": marker_index, **overlay_box})
            card["index"] = marker_index
            cards.append(card)

        if crop_concurrency == 1:
            for index, item in crop_indexes:
                output = await _process_single_crop(index, item)
                _append_crop_output(output)
        else:
            crop_semaphore = asyncio.Semaphore(crop_concurrency)

            async def _run_crop(
                crop_index: int, crop_item: dict
            ) -> tuple[int, dict[str, object] | None]:
                async with crop_semaphore:
                    return crop_index, await _process_single_crop(crop_index, crop_item)

            crop_outputs = await asyncio.gather(
                *[
                    asyncio.create_task(_run_crop(crop_index, crop_item))
                    for crop_index, crop_item in crop_indexes
                ]
            )
            for _, output in sorted(crop_outputs, key=lambda item: item[0]):
                _append_crop_output(output)

        results = _dedupe_products(results)
        return results, cards, numbered_boxes

    async def _store_debug(self, job_id: str, payload: dict, error: Exception | None = None) -> None:
        if error:
            payload["error"] = str(error)
        self._redis.store_debug(job_id, payload)
        if self._config.debug_dump_dir:
            self._config.debug_dump_dir.mkdir(parents=True, exist_ok=True)
            path = self._config.debug_dump_dir / f"{job_id}.json"
            await asyncio.to_thread(
                path.write_text, json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    async def _timed_call(
        self,
        job: Job | None,
        chat_id: int,
        service: str,
        func,
        *args,
        retry_attempts: int | None = None,
        retry_base_delay: float | None = None,
        retry_max_delay: float | None = None,
        **kwargs,
    ):
        start = time.perf_counter()
        result = await async_retry(
            func,
            *args,
            **kwargs,
            attempts=max(int(retry_attempts or self._settings.RETRY_ATTEMPTS), 1),
            base_delay=float(
                retry_base_delay
                if retry_base_delay is not None
                else self._settings.RETRY_BASE_DELAY
            ),
            max_delay=float(
                retry_max_delay
                if retry_max_delay is not None
                else self._settings.RETRY_MAX_DELAY
            ),
            logger=self._logger,
            label=service,
        )
        duration = time.perf_counter() - start
        cost_override = _extract_cost_override(result)
        cost = cost_override if cost_override is not None else self._service_costs.get(service, 0.0) or 0.0
        if cost:
            self._redis.record_cost(service, cost)
            if job is not None:
                job.costs[service] = job.costs.get(service, 0.0) + cost
        job_id = job.job_id if job is not None else None
        self._logger.info(
            "User %s job=%s: %s %.2fs -> ok",
            chat_id,
            job_id,
            service,
            duration,
        )
        return result


def _dedupe_products(products: list[ProductResult]) -> list[ProductResult]:
    seen = set()
    unique: list[ProductResult] = []
    for item in products:
        key = item.url.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


_SENSITIVE_QUERY_KEYS = (
    "api_key",
    "x-goog-signature",
    "x-goog-credential",
    "x-goog-date",
    "x-goog-signedheaders",
    "x-goog-expires",
    "token",
    "signature",
)
_URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")


def _sanitize_url(raw_url: str) -> str:
    try:
        parts = urlsplit(raw_url)
    except Exception:
        return raw_url
    if not parts.query:
        return raw_url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "<redacted>", parts.fragment))


def _sanitize_error_text(text: str, max_len: int = 300) -> str:
    if not text:
        return text
    result = text
    for key in _SENSITIVE_QUERY_KEYS:
        result = re.sub(
            rf"(?i)({re.escape(key)}=)([^&\s]+)",
            rf"\1<redacted>",
            result,
        )
    for match in _URL_PATTERN.findall(result):
        sanitized = _sanitize_url(match)
        if sanitized != match:
            result = result.replace(match, sanitized)
    if len(result) <= max_len:
        return result
    return result[: max_len - 3] + "..."


def _token_rank_fallback_score(candidate: SearchCandidate) -> float:
    position_penalty = min(max(int(candidate.position or 0), 1), 1000) / 1000.0
    include_bonus = 1.0 if candidate.include_match else 0.0
    return include_bonus + float(candidate.token_score) - position_penalty


def _select_global_top_links(
    *,
    scored_by_market: dict[str, list[tuple[SearchCandidate, float | None]]],
    market_order: list[str],
    limit: int,
    reserve_requires_score: bool = False,
) -> list[tuple[str, SearchCandidate, float | None]]:
    if limit <= 0:
        return []

    normalized_by_market: dict[str, list[tuple[SearchCandidate, float | None]]] = {}
    for market, entries in scored_by_market.items():
        valid_entries = [
            (candidate, score)
            for candidate, score in entries
            if isinstance(candidate, SearchCandidate) and candidate.url
        ]
        valid_entries.sort(
            key=lambda item: (
                -1.0 if item[1] is None else -float(item[1]),
                item[0].position,
            )
        )
        normalized_by_market[market] = valid_entries

    selected: list[tuple[str, SearchCandidate, float | None]] = []
    seen_urls: set[str] = set()

    # Reserve one candidate per marketplace (if available).
    for market in market_order:
        entries = normalized_by_market.get(market, [])
        if not entries:
            continue
        for candidate, score in entries:
            if reserve_requires_score and score is None:
                continue
            key = candidate.url.strip().lower()
            if not key or key in seen_urls:
                continue
            selected.append((market, candidate, score))
            seen_urls.add(key)
            break
        if len(selected) >= limit:
            return selected[:limit]

    remaining: list[tuple[str, SearchCandidate, float | None]] = []
    for market in market_order:
        for candidate, score in normalized_by_market.get(market, []):
            key = candidate.url.strip().lower()
            if not key or key in seen_urls:
                continue
            remaining.append((market, candidate, score))
    remaining.sort(
        key=lambda item: (
            -1.0 if item[2] is None else -float(item[2]),
            item[1].position,
        )
    )
    for market, candidate, score in remaining:
        selected.append((market, candidate, score))
        seen_urls.add(candidate.url.strip().lower())
        if len(selected) >= limit:
            break
    return selected[:limit]


def _build_search_query(domain: str, query_terms: list[str]) -> str:
    terms: list[str] = []
    seen: set[str] = set()
    for term in query_terms:
        cleaned = (term or "").strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        terms.append(cleaned)
    if not terms:
        return domain
    return f"{domain} {' '.join(terms)}"


def _format_furniture_summary(cards: list[dict]) -> str:
    if not cards:
        return "По фото не удалось найти подходящие товары в OZON, WB и Яндекс Маркете."

    source_labels = {
        "ozon": "OZON",
        "wildberries": "WB",
        "yandex_market": "YM",
    }
    lines: list[str] = ["Нашел подходящие позиции по объектам"]
    for card in cards:
        index = card.get("index")
        label = card.get("label") if isinstance(card.get("label"), str) else "Объект"
        links = card.get("links") if isinstance(card.get("links"), dict) else {}
        ranked_links = (
            card.get("ranked_links")
            if isinstance(card.get("ranked_links"), list)
            else []
        )
        lines.append(f"<b>{index}) {html.escape(label)}</b>")
        ranked_anchors: list[str] = []
        for item in ranked_links[:5]:
            if not isinstance(item, dict):
                continue
            marketplace = str(item.get("marketplace") or "").strip().lower()
            url = str(item.get("url") or "").strip()
            if not marketplace or not url:
                continue
            source = source_labels.get(marketplace, marketplace.upper())
            ranked_anchors.append(
                f'<a href="{html.escape(url, quote=True)}">{source}</a>'
            )
        if ranked_anchors:
            lines.append(" | ".join(ranked_anchors))
            lines.append("")
            continue
        object_has_links = False
        for source in ("wildberries", "ozon", "yandex_market"):
            values = links.get(source) if isinstance(links, dict) else None
            if not isinstance(values, list) or not values:
                continue
            anchors: list[str] = []
            for idx, link in enumerate(values[:3], start=1):
                if not isinstance(link, str):
                    continue
                url = link.strip()
                if not url:
                    continue
                anchors.append(f'<a href="{html.escape(url, quote=True)}">{idx}</a>')
            if anchors:
                object_has_links = True
                lines.append(f"{source_labels[source]}: " + " | ".join(anchors))
        if not object_has_links:
            lines.append("Ссылки не найдены")
        lines.append("")
    if len(lines) == 1:
        return "Объекты найдены, но подходящие товарные ссылки не нашлись."
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _extract_cost_override(result: object) -> float | None:
    cost = getattr(result, "cost_usd", None)
    if isinstance(cost, (int, float)) and cost > 0:
        return float(cost)
    return None


def _extract_image_cost_total(simple_debug: dict | None) -> float | None:
    if not isinstance(simple_debug, dict):
        return None
    direct = simple_debug.get("image_cost_total_usd")
    if isinstance(direct, (int, float)):
        return float(direct)
    total = 0.0
    found = False
    for key in ("render_cost_usd", "rerender_cost_usd", "fix_cost_usd"):
        value = simple_debug.get(key)
        if isinstance(value, (int, float)):
            total += float(value)
            found = True
    if found:
        return total
    return None


def _compute_score(scores: dict | None) -> int | None:
    if not isinstance(scores, dict):
        return None
    geometry = scores.get("geometry")
    request = scores.get("request")
    function = scores.get("function")
    if geometry is None or request is None or function is None:
        return None
    return int(geometry) * 10000 + int(request) * 100 + int(function)


def _to_utc_iso(value) -> str | None:
    if value is None:
        return None
    try:
        return value.replace(tzinfo=None).isoformat() + "Z"
    except Exception:
        return None


def _unix_to_utc_iso(timestamp: float | int | None) -> str | None:
    if timestamp is None:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(timestamp)))
    except Exception:
        return None


def _attach_queue_metadata(
    metadata_json: dict | None,
    *,
    queue_wait_seconds: float,
    total_elapsed_seconds: float,
    queued_at,
    run_started_unix: float,
) -> dict:
    metadata = dict(metadata_json) if isinstance(metadata_json, dict) else {}
    metadata["queue"] = {
        "wait_seconds": round(max(queue_wait_seconds, 0.0), 3),
        "queued_at": _to_utc_iso(queued_at),
        "started_at": _unix_to_utc_iso(run_started_unix),
        "total_elapsed_seconds": round(max(total_elapsed_seconds, 0.0), 3),
    }
    return metadata


def _build_providers_json(debug: dict) -> dict | None:
    if not isinstance(debug, dict):
        return None
    providers = {
        "planner": debug.get("planner_provider"),
        "render": debug.get("render_provider"),
        "ranker": debug.get("ranker_provider"),
        "validator": debug.get("validator_provider"),
        "rerender": debug.get("rerender_provider") or debug.get("fix_provider"),
        "rerender_validator": debug.get("rerender_validator_provider")
        or debug.get("fix_validator_provider"),
    }
    providers = {k: v for k, v in providers.items() if v}
    return providers or None


def _build_metadata_json(
    simple_debug: dict | None,
    objects_count: int | None,
    object_cards_count: int | None,
    products_count: int | None,
) -> dict | None:
    if not isinstance(simple_debug, dict):
        simple_debug = {}

    timings = simple_debug.get("timings_s") if isinstance(simple_debug.get("timings_s"), dict) else None
    planner_usage = (
        simple_debug.get("planner_usage")
        if isinstance(simple_debug.get("planner_usage"), dict)
        else None
    )
    ranker_usage = (
        simple_debug.get("ranker_usage")
        if isinstance(simple_debug.get("ranker_usage"), dict)
        else None
    )
    validator_usage = (
        simple_debug.get("validator_usage")
        if isinstance(simple_debug.get("validator_usage"), dict)
        else None
    )
    render_validation = (
        simple_debug.get("render_validation")
        if isinstance(simple_debug.get("render_validation"), dict)
        else {}
    )
    rerender_validator_usage = (
        simple_debug.get("rerender_validator_usage")
        if isinstance(simple_debug.get("rerender_validator_usage"), dict)
        else (
            simple_debug.get("fix_validator_usage")
            if isinstance(simple_debug.get("fix_validator_usage"), dict)
            else None
        )
    )
    rerender_validation = (
        simple_debug.get("rerender_validation")
        if isinstance(simple_debug.get("rerender_validation"), dict)
        else (
            simple_debug.get("fix_validation")
            if isinstance(simple_debug.get("fix_validation"), dict)
            else {}
        )
    )
    validation = {
        "render_ok": bool(render_validation.get("request_ok"))
        and bool(render_validation.get("geometry_ok"))
        and bool(render_validation.get("function_ok")),
        "rerender_ok": bool(rerender_validation.get("request_ok"))
        and bool(rerender_validation.get("geometry_ok"))
        and bool(rerender_validation.get("function_ok")),
        "best_ok": bool(simple_debug.get("best_ok")),
    }
    planner_schema = (
        simple_debug.get("planner_schema")
        if isinstance(simple_debug.get("planner_schema"), dict)
        else None
    )
    planner_parse_mode = (
        str(simple_debug.get("planner_parse_mode"))
        if simple_debug.get("planner_parse_mode") is not None
        else None
    )
    planner_text_fallback_used = bool(simple_debug.get("planner_text_fallback_used"))
    ranker_schema = (
        simple_debug.get("ranker_schema")
        if isinstance(simple_debug.get("ranker_schema"), dict)
        else None
    )
    ranker_parse_mode = (
        str(simple_debug.get("ranker_parse_mode"))
        if simple_debug.get("ranker_parse_mode") is not None
        else None
    )
    validator_schema = (
        simple_debug.get("validator_schema")
        if isinstance(simple_debug.get("validator_schema"), dict)
        else None
    )
    rerender_validator_schema = (
        simple_debug.get("rerender_validator_schema")
        if isinstance(simple_debug.get("rerender_validator_schema"), dict)
        else (
            simple_debug.get("fix_validator_schema")
            if isinstance(simple_debug.get("fix_validator_schema"), dict)
            else None
        )
    )
    validator_parse_mode = (
        str(simple_debug.get("validator_parse_mode"))
        if simple_debug.get("validator_parse_mode") is not None
        else None
    )
    rerender_validator_parse_mode = (
        str(simple_debug.get("rerender_validator_parse_mode"))
        if simple_debug.get("rerender_validator_parse_mode") is not None
        else (
            str(simple_debug.get("fix_validator_parse_mode"))
            if simple_debug.get("fix_validator_parse_mode") is not None
            else None
        )
    )
    input_prepared = (
        simple_debug.get("input_prepared")
        if isinstance(simple_debug.get("input_prepared"), dict)
        else None
    )
    # Keep metadata compact and query-friendly for DB UI.
    metadata = {
        "simple_pipeline": {
            "best_label": simple_debug.get("best_label"),
            "input_prepared": input_prepared,
            "timings_s": timings,
            "scores": {
                "render": _compute_score(render_validation.get("scores")),
                "rerender": _compute_score(rerender_validation.get("scores")),
            },
            "costs": {
                "render_usd": simple_debug.get("render_cost_usd"),
                "rerender_usd": simple_debug.get("rerender_cost_usd")
                if simple_debug.get("rerender_cost_usd") is not None
                else simple_debug.get("fix_cost_usd"),
                "ranker_usd": simple_debug.get("ranker_cost_usd"),
                "image_total_usd": simple_debug.get("image_cost_total_usd"),
                "image_sources": simple_debug.get("image_cost_sources"),
            },
            "tokens": {
                "planner": planner_usage,
                "ranker": ranker_usage,
                "validator": validator_usage,
                "rerender_validator": rerender_validator_usage,
            },
            "validation": validation,
            "planner_block": {
                "blocked": bool(simple_debug.get("planner_blocked")),
                "reason": simple_debug.get("planner_block_reason"),
                "message": simple_debug.get("planner_block_message"),
            },
            "style_reference": {
                "enabled": bool(simple_debug.get("style_reference_enabled")),
                "used": bool(simple_debug.get("style_ref_used")),
                "source": simple_debug.get("style_ref_source"),
                "status": simple_debug.get("style_reference_status"),
                "prepared": (
                    simple_debug.get("style_reference_prepared")
                    if isinstance(simple_debug.get("style_reference_prepared"), dict)
                    else None
                ),
            },
            "ranker": {
                "best": (
                    simple_debug.get("ranker_ab", {}).get("best")
                    if isinstance(simple_debug.get("ranker_ab"), dict)
                    else None
                ),
                "confidence": (
                    simple_debug.get("ranker_ab", {}).get("confidence")
                    if isinstance(simple_debug.get("ranker_ab"), dict)
                    else None
                ),
                "both_failed": (
                    simple_debug.get("ranker_ab", {}).get("both_failed")
                    if isinstance(simple_debug.get("ranker_ab"), dict)
                    else None
                ),
                "fallback_reason": simple_debug.get("ranker_fallback_reason"),
            },
            "planner_parser": {
                "parse_mode": planner_parse_mode,
                "text_fallback_used": planner_text_fallback_used,
                "schema": planner_schema,
            },
            "ranker_parser": {
                "parse_mode": ranker_parse_mode,
                "schema": ranker_schema,
            },
            "validator_parser": {
                "render_parse_mode": validator_parse_mode,
                "rerender_parse_mode": rerender_validator_parse_mode,
                "render_invalid_json": bool(simple_debug.get("validator_invalid_json")),
                "rerender_invalid_json": bool(
                    simple_debug.get("rerender_validator_invalid_json")
                    if simple_debug.get("rerender_validator_invalid_json") is not None
                    else simple_debug.get("fix_validator_invalid_json")
                ),
                "render_schema": validator_schema,
                "rerender_schema": rerender_validator_schema,
            },
        },
        "search": {
            "objects_count": objects_count,
            "object_cards_count": object_cards_count,
            "products_count": products_count,
        },
    }
    return metadata


def _compute_total_cost(job: Job | None, debug: dict) -> float | None:
    total = 0.0
    found = False
    if job and isinstance(job.costs, dict):
        for value in job.costs.values():
            if isinstance(value, (int, float)):
                total += float(value)
                found = True
    for key in (
        "planner_cost_usd",
        "ranker_cost_usd",
        "validator_cost_usd",
        "rerender_validator_cost_usd",
        "fix_validator_cost_usd",
    ):
        value = debug.get(key)
        if isinstance(value, (int, float)):
            total += float(value)
            found = True
    return total if found else None


def _parse_label_list(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _mask_style_ref_url(url: str | None) -> str | None:
    if not isinstance(url, str):
        return None
    trimmed = url.strip()
    if not trimmed:
        return None
    base = trimmed.split("?", 1)[0]
    if len(base) <= 96:
        return base
    return f"{base[:64]}...{base[-24:]}"


def _resolve_style_ref_fields(
    *,
    style_reference_requested: bool,
    style_reference_url: str | None,
    simple_debug: dict[str, object] | None,
) -> tuple[bool, str, str | None, str]:
    debug = simple_debug if isinstance(simple_debug, dict) else {}
    used_raw = debug.get("style_ref_used")
    if used_raw is None:
        used_raw = debug.get("style_reference_enabled")
    used = bool(used_raw)
    source = (
        str(debug.get("style_ref_source"))
        if debug.get("style_ref_source") is not None
        else ("telegram_user_photo" if style_reference_requested else "none")
    )
    status = (
        str(debug.get("style_reference_status"))
        if debug.get("style_reference_status") is not None
        else ("requested" if style_reference_requested else "not_requested")
    )
    return used, source, _mask_style_ref_url(style_reference_url), status


def _derive_design_success_status(mode: str, simple_debug: dict[str, object] | None) -> str:
    if mode == MODE_FURNITURE_SEARCH:
        return "success"
    debug = simple_debug if isinstance(simple_debug, dict) else {}
    return "degraded_success" if bool(debug.get("degraded")) else "success"
