"""Web jobs application service."""
from __future__ import annotations

import logging
from uuid import UUID

from app_services.analytics.events import EVENT_JOB_COMPLETED, EVENT_JOB_FAILED, EVENT_JOB_STALE
from app_services.analytics.service import append_flow_event
from app_services.billing.ledger import (
    release_account_credit_reservation,
    reserve_account_credits,
)
from config import Settings
from models.design_draft_model import DesignDraft
from models.furniture_search_draft_model import FurnitureSearchDraft
from models.job_model import Job as DbJob
from models.schemas import Job as RuntimeJob
from pipeline.orchestrator import MODE_FURNITURE_SEARCH, MODE_RENDER_ONLY, PipelineOrchestrator
from services.cloud_tasks import CloudTasksQueue
from services.db_connection import get_db_session
from services.repositories.design_repository import DesignRepository
from services.storage import S3Storage
from utils.observability import emit_observability_event
from utils.time import utcnow


logger = logging.getLogger("web_jobs")


class JobsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._storage = S3Storage(settings, prefix="uploads/")

    async def create_job(self, account_id: str, *, job_type: str, draft_id: str) -> dict:
        with get_db_session() as session:
            account_uuid = UUID(account_id)
            draft_uuid = UUID(draft_id)
            normalized_job_type = str(job_type or "").strip().lower()
            draft_type = None
            units_reserved = 0
            if normalized_job_type == "design":
                draft = (
                    session.query(DesignDraft)
                    .filter(
                        DesignDraft.id == draft_uuid,
                        DesignDraft.account_id == account_uuid,
                    )
                    .first()
                )
                if draft is None:
                    return {"status": "draft_not_found"}
                draft_type = "design"
                units_reserved = int(draft.estimated_units or 0)
            elif normalized_job_type == "furniture_search":
                draft = (
                    session.query(FurnitureSearchDraft)
                    .filter(
                        FurnitureSearchDraft.id == draft_uuid,
                        FurnitureSearchDraft.account_id == account_uuid,
                    )
                    .first()
                )
                if draft is None:
                    return {"status": "draft_not_found"}
                draft_type = "furniture_search"
                units_reserved = int(draft.estimated_units or 0)
            else:
                return {"status": "invalid_job_type"}

            reserve = reserve_account_credits(
                session,
                account_id=account_uuid,
                units=units_reserved,
                reason=f"job_{normalized_job_type}",
                meta={
                    "job_type": normalized_job_type,
                    "draft_id": str(draft_uuid),
                },
            )
            if reserve.get("status") != "ok":
                return {
                    "status": str(reserve.get("status")),
                    "balance": {
                        "credits": int(reserve.get("balance_after") or reserve.get("balance_before") or 0)
                    },
                }

            job = DbJob(
                account_id=account_uuid,
                job_type=normalized_job_type,
                status="queued",
                draft_id=draft_uuid,
                draft_type=draft_type,
                units_reserved=units_reserved,
                provider_meta_json={
                    "billing_event_id": reserve.get("billing_event_id"),
                    "balance_after": reserve.get("balance_after"),
                    "reservation_released": False,
                },
                progress_meta_json={"stage": "queued"},
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            return {"status": "ok", "job": _serialize_job(job)}

    async def enqueue_job(self, job_id: str) -> None:
        queue = CloudTasksQueue(self._settings)
        worker_url = (self._settings.CLOUD_TASKS_WORKER_URL or "").rstrip("/")
        if worker_url.endswith("/tasks/telegram"):
            worker_url = worker_url[: -len("/tasks/telegram")]
        target_url = f"{worker_url}/tasks/web-job" if worker_url else None
        await queue.enqueue(
            {"job_id": job_id},
            task_id=f"web-job-{job_id}",
            target_url=target_url,
        )

    async def get_job(self, account_id: str, job_id: str) -> dict | None:
        with get_db_session() as session:
            account_uuid = UUID(account_id)
            job_uuid = UUID(job_id)
            job = (
                session.query(DbJob)
                .filter(
                    DbJob.id == job_uuid,
                    DbJob.account_id == account_uuid,
                )
                .with_for_update()
                .first()
            )
            if job is None:
                return None
            self._reconcile_stale_job(session, job)
            session.commit()
            session.refresh(job)
            return _serialize_job(job)

    async def cancel_job_before_start(
        self,
        job_id: str,
        *,
        error_code: str,
        error_message: str,
        error_stage: str = "enqueue",
    ) -> dict | None:
        with get_db_session() as session:
            job = session.query(DbJob).filter(DbJob.id == UUID(job_id)).with_for_update().first()
            if job is None:
                return None
            if job.status not in {"queued", "processing"}:
                return _serialize_job(job)
            self._mark_job_failed(
                session,
                job,
                error_code=error_code,
                error_message=error_message,
                error_stage=error_stage,
                progress_stage="failed",
                release_reason="job_canceled_before_start",
            )
            return _serialize_job(job)

    async def run_job_async(self, job_id: str, orchestrator: PipelineOrchestrator) -> dict:
        with get_db_session() as session:
            job = session.query(DbJob).filter(DbJob.id == UUID(job_id)).with_for_update().first()
            if job is None:
                return {"status": "not_found"}
            self._reconcile_stale_job(session, job)
            if job.status not in {"queued", "processing"}:
                session.commit()
                return {"status": "skipped", "job_status": job.status}

            mode = MODE_RENDER_ONLY if job.job_type == "design" else MODE_FURNITURE_SEARCH
            job.status = "processing"
            job.started_at = utcnow()
            job.progress_meta_json = {"stage": "processing", "mode": mode}

            if job.job_type == "design":
                draft = session.query(DesignDraft).filter(DesignDraft.id == job.draft_id).first()
                if draft is None:
                    self._mark_job_failed(
                        session,
                        job,
                        error_code="DRAFT_NOT_FOUND",
                        error_message="Design draft not found.",
                        error_stage="draft",
                        progress_stage="failed",
                        release_reason="job_failed_draft_missing",
                    )
                    return {"status": "failed"}
                source_key = draft.source_file.storage_key if draft.source_file else None
                style_key = draft.style_reference_file.storage_key if draft.style_reference_file else None
                prompt = draft.user_request
            else:
                draft = (
                    session.query(FurnitureSearchDraft)
                    .filter(FurnitureSearchDraft.id == job.draft_id)
                    .first()
                )
                if draft is None:
                    self._mark_job_failed(
                        session,
                        job,
                        error_code="DRAFT_NOT_FOUND",
                        error_message="Furniture draft not found.",
                        error_stage="draft",
                        progress_stage="failed",
                        release_reason="job_failed_draft_missing",
                    )
                    return {"status": "failed"}
                source_key = draft.source_file.storage_key if draft.source_file else None
                style_key = None
                prompt = draft.user_request or ""

            if not source_key:
                self._mark_job_failed(
                    session,
                    job,
                    error_code="SOURCE_FILE_NOT_FOUND",
                    error_message="Source file is missing.",
                    error_stage="input",
                    progress_stage="failed",
                    release_reason="job_failed_source_missing",
                )
                return {"status": "failed"}

            source_bytes = self._storage.download_bytes(source_key)
            style_bytes = self._storage.download_bytes(style_key) if style_key else None
            units_reserved = int(job.units_reserved or 0)
            runtime_account_id = str(job.account_id)
            runtime_draft_id = _design_record_draft_id(job)
            session.commit()

        runtime_job = RuntimeJob(
            job_id=str(job_id),
            chat_id=0,
            status="queued",
            mode=mode,
            units_spent=units_reserved,
            account_id=runtime_account_id,
            draft_id=runtime_draft_id,
            user_prompt=prompt,
        )
        try:
            await orchestrator._run_job(
                runtime_job,
                source_bytes,
                prompt,
                style_bytes,
                None,
                mode,
                queue_wait_seconds=0.0,
            )
        except Exception as exc:
            logger.exception("web_job_execution_failed job_id=%s", job_id)
            emit_observability_event(
                logger,
                "web_job_execution_failed",
                level="error",
                job_id=str(job_id),
                job_type=mode,
                error_message=str(exc),
                exc_info=exc,
            )
            with get_db_session() as session:
                db_job = session.query(DbJob).filter(DbJob.id == UUID(job_id)).with_for_update().first()
                if db_job is not None:
                    self._mark_job_failed(
                        session,
                        db_job,
                        error_code="WORKER_EXCEPTION",
                        error_message=str(exc),
                        error_stage="worker",
                        progress_stage="failed",
                        release_reason="job_failed_worker_exception",
                    )
            return {"status": "failed"}

        with get_db_session() as session:
            db_job = session.query(DbJob).filter(DbJob.id == UUID(job_id)).with_for_update().first()
            if db_job is None:
                return {"status": "not_found"}

            design = DesignRepository(session).get_by_job_id(UUID(job_id))
            db_job.result_ref_type = "design" if design is not None else None
            db_job.result_ref_id = design.id if design is not None else None
            db_job.units_final = db_job.units_reserved
            db_job.ended_at = utcnow()
            if runtime_job.status == "done":
                db_job.status = "completed"
                db_job.progress_meta_json = {"stage": "completed"}
                append_flow_event(
                    session,
                    account_id=db_job.account_id,
                    event_type=EVENT_JOB_COMPLETED,
                    screen_key="jobs",
                    action_key="job_completed",
                    source="worker",
                    meta={
                        "job_id": str(db_job.id),
                        "job_type": db_job.job_type,
                        "result_ref_id": str(db_job.result_ref_id) if db_job.result_ref_id else None,
                    },
                )
                session.commit()
                session.refresh(db_job)
            else:
                self._mark_job_failed(
                    session,
                    db_job,
                    error_code="JOB_FAILED",
                    error_message=str(runtime_job.debug.get("error") or "Job failed."),
                    error_stage="runtime",
                    progress_stage="failed",
                    release_reason="job_failed_runtime",
                )
            return {"status": db_job.status, "job": _serialize_job(db_job)}

    def _reconcile_stale_job(self, session, job: DbJob) -> None:
        if job.status not in {"queued", "processing"}:
            return

        now = utcnow()
        if job.status == "queued":
            age_seconds = (now - (job.created_at or now)).total_seconds()
            if age_seconds >= int(self._settings.WEB_JOB_QUEUE_STALE_SECONDS or 0):
                self._mark_job_failed(
                    session,
                    job,
                    error_code="JOB_STALE",
                    error_message="Задача слишком долго оставалась в очереди и была остановлена. Кредиты возвращены на баланс.",
                    error_stage="queue",
                    progress_stage="stale",
                    release_reason="job_stale_queue",
                )
            return

        started_at = job.started_at or job.created_at or now
        age_seconds = (now - started_at).total_seconds()
        if age_seconds >= int(self._settings.WEB_JOB_PROCESSING_STALE_SECONDS or 0):
            self._mark_job_failed(
                session,
                job,
                error_code="JOB_STALE",
                error_message="Задача обрабатывалась слишком долго и была остановлена. Кредиты возвращены на баланс.",
                error_stage="processing",
                progress_stage="stale",
                release_reason="job_stale_processing",
            )

    def _mark_job_failed(
        self,
        session,
        job: DbJob,
        *,
        error_code: str,
        error_message: str,
        error_stage: str | None,
        progress_stage: str,
        release_reason: str,
    ) -> None:
        emit_observability_event(
            logger,
            "web_job_marked_failed",
            level="warning" if error_code == "JOB_STALE" else "error",
            job_id=str(job.id),
            account_id=str(job.account_id) if job.account_id else None,
            job_type=job.job_type,
            error_code=error_code,
            error_stage=error_stage,
            release_reason=release_reason,
            units_reserved=int(job.units_reserved or 0),
        )
        job.status = "failed"
        job.error_code = error_code
        job.error_message = error_message
        job.error_stage = error_stage
        job.ended_at = utcnow()
        job.progress_meta_json = {
            "stage": progress_stage,
            "release_reason": release_reason,
        }
        self._release_reserved_credits(session, job, release_reason=release_reason)
        append_flow_event(
            session,
            account_id=job.account_id,
            event_type=EVENT_JOB_STALE if error_code == "JOB_STALE" else EVENT_JOB_FAILED,
            screen_key="jobs",
            action_key="job_failed",
            source="worker",
            meta={
                "job_id": str(job.id),
                "job_type": job.job_type,
                "error_code": error_code,
                "error_stage": error_stage,
                "release_reason": release_reason,
                "credits_released": bool((job.provider_meta_json or {}).get("reservation_released")),
            },
        )
        session.commit()
        session.refresh(job)

    def _release_reserved_credits(self, session, job: DbJob, *, release_reason: str) -> None:
        meta = dict(job.provider_meta_json or {})
        if meta.get("reservation_released"):
            return
        units_reserved = int(job.units_reserved or 0)
        if units_reserved <= 0 or job.account_id is None:
            meta["reservation_released"] = True
            meta["reservation_release_reason"] = release_reason
            job.provider_meta_json = meta
            return

        release = release_account_credit_reservation(
            session,
            account_id=job.account_id,
            units=units_reserved,
            reason=release_reason,
            meta={
                "job_id": str(job.id),
                "job_type": job.job_type,
                "draft_id": str(job.draft_id) if job.draft_id else None,
                "billing_event_id": meta.get("billing_event_id"),
            },
        )
        meta["reservation_released"] = release.get("status") == "ok"
        meta["reservation_release_reason"] = release_reason
        meta["reservation_release_event_id"] = release.get("billing_event_id")
        meta["reservation_released_at"] = utcnow().isoformat()
        meta["balance_after_release"] = release.get("balance_after")
        job.provider_meta_json = meta


def _serialize_job(job: DbJob) -> dict:
    provider_meta = job.provider_meta_json or {}
    return {
        "id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "draft_id": str(job.draft_id) if job.draft_id else None,
        "draft_type": job.draft_type,
        "result_ref_type": job.result_ref_type,
        "result_ref_id": str(job.result_ref_id) if job.result_ref_id else None,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "error_stage": job.error_stage,
        "units_reserved": job.units_reserved,
        "units_final": job.units_final,
        "progress": job.progress_meta_json or {},
        "created_at": job.created_at,
        "started_at": job.started_at,
        "ended_at": job.ended_at,
        "stale": job.error_code == "JOB_STALE",
        "credits_released": bool(provider_meta.get("reservation_released")),
    }


def _design_record_draft_id(job: DbJob) -> str | None:
    if job.job_type != "design" or job.draft_id is None:
        return None
    return str(job.draft_id)
