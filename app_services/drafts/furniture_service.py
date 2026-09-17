"""Furniture draft service scaffold."""
from __future__ import annotations

import asyncio
from uuid import UUID

from app_services.media_urls import MediaUrlResolver
from config import Settings
from models.furniture_search_draft_model import FurnitureSearchDraft
from models.uploaded_file_model import UploadedFile
from services.db_connection import get_db_session


class FurnitureDraftService:
    def __init__(self, settings: Settings) -> None:
        self._media_urls = MediaUrlResolver(settings)

    async def create_draft(self, account_id: str, payload: dict) -> dict:
        return await asyncio.to_thread(self._create_draft_sync, account_id, payload)

    async def list_drafts(self, account_id: str, limit: int = 6) -> list[dict]:
        return await asyncio.to_thread(self._list_drafts_sync, account_id, limit)

    async def get_draft(self, account_id: str, draft_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_draft_sync, account_id, draft_id)

    async def update_draft(self, account_id: str, draft_id: str, payload: dict) -> dict | None:
        return await asyncio.to_thread(self._update_draft_sync, account_id, draft_id, payload)

    async def delete_draft(self, account_id: str, draft_id: str) -> bool:
        return await asyncio.to_thread(self._delete_draft_sync, account_id, draft_id)

    async def get_reuse_payload(self, account_id: str, result_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_reuse_payload_sync, account_id, result_id)

    def _create_draft_sync(self, account_id: str, payload: dict) -> dict:
        with get_db_session() as session:
            source_file = _get_owned_file(session, account_id, payload["source_file_id"])
            if source_file is None:
                return {"status": "source_not_found"}
            draft = FurnitureSearchDraft(
                account_id=UUID(account_id),
                source_file_id=source_file.id,
                source_image_url=source_file.file_url,
                prepared_image_url=None,
                user_request=str(payload.get("user_request") or "").strip() or None,
                settings_json=payload.get("settings_json"),
                estimated_units=1,
                status="ready",
            )
            session.add(draft)
            session.commit()
            session.refresh(draft)
            return {"status": "ok", "draft": self._serialize_furniture_draft(draft)}

    def _get_draft_sync(self, account_id: str, draft_id: str) -> dict | None:
        with get_db_session() as session:
            draft = (
                session.query(FurnitureSearchDraft)
                .filter(
                    FurnitureSearchDraft.id == UUID(draft_id),
                    FurnitureSearchDraft.account_id == UUID(account_id),
                )
                .first()
            )
            if draft is None:
                return None
            return self._serialize_furniture_draft(draft)

    def _list_drafts_sync(self, account_id: str, limit: int) -> list[dict]:
        with get_db_session() as session:
            drafts = (
                session.query(FurnitureSearchDraft)
                .filter(FurnitureSearchDraft.account_id == UUID(account_id))
                .order_by(FurnitureSearchDraft.updated_at.desc(), FurnitureSearchDraft.created_at.desc())
                .limit(max(min(int(limit or 6), 20), 1))
                .all()
            )
            return [self._serialize_furniture_draft(draft) for draft in drafts]

    def _update_draft_sync(self, account_id: str, draft_id: str, payload: dict) -> dict | None:
        with get_db_session() as session:
            draft = (
                session.query(FurnitureSearchDraft)
                .filter(
                    FurnitureSearchDraft.id == UUID(draft_id),
                    FurnitureSearchDraft.account_id == UUID(account_id),
                )
                .first()
            )
            if draft is None:
                return None
            if "user_request" in payload:
                draft.user_request = str(payload.get("user_request") or "").strip() or None
            session.commit()
            session.refresh(draft)
            return self._serialize_furniture_draft(draft)

    def _delete_draft_sync(self, account_id: str, draft_id: str) -> bool:
        with get_db_session() as session:
            draft = (
                session.query(FurnitureSearchDraft)
                .filter(
                    FurnitureSearchDraft.id == UUID(draft_id),
                    FurnitureSearchDraft.account_id == UUID(account_id),
                )
                .first()
            )
            if draft is None:
                return False
            session.delete(draft)
            session.commit()
            return True

    def _get_reuse_payload_sync(self, account_id: str, result_id: str) -> dict | None:
        from models.design_model import Design

        with get_db_session() as session:
            design = (
                session.query(Design)
                .filter(
                    Design.id == UUID(result_id),
                    Design.account_id == UUID(account_id),
                )
                .first()
            )
            if design is None:
                return None
            draft = None
            if design.draft is not None and design.draft.source_file_id is not None:
                draft = design.draft
            else:
                job = getattr(design, "job", None)
                if job is not None and getattr(job, "draft_type", None) == "furniture_search" and getattr(job, "draft_id", None):
                    draft = (
                        session.query(FurnitureSearchDraft)
                        .filter(
                            FurnitureSearchDraft.id == job.draft_id,
                            FurnitureSearchDraft.account_id == UUID(account_id),
                        )
                        .first()
                    )
            if draft is None or draft.source_file_id is None:
                return None
            return self._media_urls.resolve_many({
                "source_file_id": str(draft.source_file_id),
                "source_image_url": draft.source_image_url,
                "user_request": design.user_request or draft.user_request,
                "estimated_units": int(draft.estimated_units or 1),
            }, "source_image_url")

    def _serialize_furniture_draft(self, draft: FurnitureSearchDraft) -> dict:
        return self._media_urls.resolve_many(_serialize_furniture_draft(draft), "source_image_url")


def _get_owned_file(session, account_id: str, file_id: str) -> UploadedFile | None:
    return (
        session.query(UploadedFile)
        .filter(
            UploadedFile.id == UUID(file_id),
            UploadedFile.account_id == UUID(account_id),
            UploadedFile.status == "ready",
        )
        .first()
    )


def _serialize_furniture_draft(draft: FurnitureSearchDraft) -> dict:
    return {
        "id": str(draft.id),
        "status": draft.status,
        "source_file_id": str(draft.source_file_id) if draft.source_file_id else None,
        "source_image_url": draft.source_image_url,
        "user_request": draft.user_request,
        "estimated_units": draft.estimated_units,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }
