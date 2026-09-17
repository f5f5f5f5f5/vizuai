"""Design draft service scaffold."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from uuid import UUID

from app_services.media_urls import MediaUrlResolver
from config import Settings
from models.design_draft_model import DesignDraft
from models.uploaded_file_model import UploadedFile
from services.db_connection import get_db_session
from services.storage import S3Storage


class DesignDraftService:
    def __init__(self, settings: Settings) -> None:
        self._media_urls = MediaUrlResolver(settings)
        self._storage = S3Storage(settings, prefix="uploads/")

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

    async def get_edit_payload(self, account_id: str, result_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_edit_payload_sync, account_id, result_id)

    async def get_furniture_seed_payload(self, account_id: str, result_id: str) -> dict | None:
        return await asyncio.to_thread(self._get_furniture_seed_payload_sync, account_id, result_id)

    def _create_draft_sync(self, account_id: str, payload: dict) -> dict:
        with get_db_session() as session:
            source_file = _get_owned_file(session, account_id, payload["source_file_id"])
            if source_file is None:
                return {"status": "source_not_found"}
            style_file = None
            style_reference_file_id = payload.get("style_reference_file_id")
            if style_reference_file_id:
                style_file = _get_owned_file(session, account_id, style_reference_file_id)
                if style_file is None:
                    return {"status": "style_reference_not_found"}

            draft = DesignDraft(
                account_id=UUID(account_id),
                source_file_id=source_file.id,
                style_reference_file_id=(style_file.id if style_file else None),
                source_image_url=source_file.file_url,
                prepared_image_url=None,
                style_reference_image_url=(style_file.file_url if style_file else None),
                style_reference_enabled=bool(payload.get("style_reference_enabled")),
                user_request=str(payload.get("user_request") or "").strip(),
                settings_json=payload.get("settings_json"),
                estimated_units=1,
                status="ready",
            )
            session.add(draft)
            session.commit()
            session.refresh(draft)
            return {"status": "ok", "draft": self._serialize_design_draft(draft)}

    def _get_draft_sync(self, account_id: str, draft_id: str) -> dict | None:
        with get_db_session() as session:
            draft = (
                session.query(DesignDraft)
                .filter(
                    DesignDraft.id == UUID(draft_id),
                    DesignDraft.account_id == UUID(account_id),
                )
                .first()
            )
            if draft is None:
                return None
            return self._serialize_design_draft(draft)

    def _list_drafts_sync(self, account_id: str, limit: int) -> list[dict]:
        with get_db_session() as session:
            drafts = (
                session.query(DesignDraft)
                .filter(DesignDraft.account_id == UUID(account_id))
                .order_by(DesignDraft.updated_at.desc(), DesignDraft.created_at.desc())
                .limit(max(min(int(limit or 6), 20), 1))
                .all()
            )
            return [self._serialize_design_draft(draft) for draft in drafts]

    def _update_draft_sync(self, account_id: str, draft_id: str, payload: dict) -> dict | None:
        with get_db_session() as session:
            draft = (
                session.query(DesignDraft)
                .filter(
                    DesignDraft.id == UUID(draft_id),
                    DesignDraft.account_id == UUID(account_id),
                )
                .first()
            )
            if draft is None:
                return None
            if "user_request" in payload:
                draft.user_request = str(payload.get("user_request") or "").strip()
            if "style_reference_enabled" in payload:
                draft.style_reference_enabled = bool(payload.get("style_reference_enabled"))
            if "style_reference_file_id" in payload:
                style_reference_file_id = payload.get("style_reference_file_id")
                if style_reference_file_id:
                    style_file = _get_owned_file(session, account_id, style_reference_file_id)
                    if style_file is None:
                        return {"status": "style_reference_not_found"}
                    draft.style_reference_file_id = style_file.id
                    draft.style_reference_image_url = style_file.file_url
                else:
                    draft.style_reference_file_id = None
                    draft.style_reference_image_url = None
            session.commit()
            session.refresh(draft)
            return self._serialize_design_draft(draft)

    def _delete_draft_sync(self, account_id: str, draft_id: str) -> bool:
        with get_db_session() as session:
            draft = (
                session.query(DesignDraft)
                .filter(
                    DesignDraft.id == UUID(draft_id),
                    DesignDraft.account_id == UUID(account_id),
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
                    Design.mode != "furniture_search",
                )
                .with_for_update()
                .first()
            )
            if design is None or design.draft is None or design.draft.source_file_id is None:
                return None
            return self._media_urls.resolve_many({
                "source_file_id": str(design.draft.source_file_id),
                "source_image_url": design.draft.source_image_url,
                "style_reference_file_id": (
                    str(design.draft.style_reference_file_id)
                    if design.draft.style_reference_file_id
                    else None
                ),
                "style_reference_image_url": design.draft.style_reference_image_url,
                "style_reference_enabled": bool(design.draft.style_reference_enabled),
                "user_request": design.user_request,
                "estimated_units": int(design.draft.estimated_units or 1),
            }, "source_image_url", "style_reference_image_url")

    def _get_edit_payload_sync(self, account_id: str, result_id: str) -> dict | None:
        from models.design_model import Design

        with get_db_session() as session:
            design = (
                session.query(Design)
                .filter(
                    Design.id == UUID(result_id),
                    Design.account_id == UUID(account_id),
                    Design.mode != "furniture_search",
                )
                .first()
            )
            if design is None:
                return None

            edit_source_url = (
                design.final_image_url
                or design.render_image_url
                or design.fix_image_url
            )
            if not edit_source_url:
                return None

            source_file = self._get_or_create_edit_source_file(
                session,
                account_id,
                edit_source_url,
            )
            if source_file is None:
                return None

            style_file = design.draft.style_reference_file if design.draft else None
            return self._media_urls.resolve_many({
                "source_file_id": str(source_file.id),
                "source_image_url": source_file.file_url,
                "style_reference_file_id": (
                    str(style_file.id)
                    if style_file is not None
                    else None
                ),
                "style_reference_image_url": (
                    style_file.file_url
                    if style_file is not None
                    else None
                ),
                "style_reference_enabled": bool(design.draft.style_reference_enabled) if design.draft else False,
                "user_request": "",
                "estimated_units": int(design.draft.estimated_units or 1) if design.draft else 1,
            }, "source_image_url", "style_reference_image_url")

    def _get_furniture_seed_payload_sync(self, account_id: str, result_id: str) -> dict | None:
        from models.design_model import Design

        with get_db_session() as session:
            design = (
                session.query(Design)
                .filter(
                    Design.id == UUID(result_id),
                    Design.account_id == UUID(account_id),
                    Design.mode != "furniture_search",
                )
                .with_for_update()
                .first()
            )
            if design is None:
                return None

            source_url = (
                design.final_image_url
                or design.render_image_url
                or design.fix_image_url
            )
            if not source_url:
                return None

            source_file = self._get_or_create_result_source_file(
                session,
                account_id,
                source_url,
                purpose="furniture-source",
            )
            if source_file is None:
                return None

            return self._media_urls.resolve_many({
                "source_file_id": str(source_file.id),
                "source_image_url": source_file.file_url,
                "user_request": "",
                "estimated_units": 1,
            }, "source_image_url")

    def _get_or_create_edit_source_file(
        self,
        session,
        account_id: str,
        source_url: str,
    ) -> UploadedFile | None:
        return self._get_or_create_result_source_file(
            session,
            account_id,
            source_url,
            purpose="design-edit-source",
        )

    def _get_or_create_result_source_file(
        self,
        session,
        account_id: str,
        source_url: str,
        *,
        purpose: str,
    ) -> UploadedFile | None:
        source_key = self._media_urls.extract_storage_key(source_url)
        if not source_key:
            return None
        filename = _result_source_filename(source_key, purpose)
        existing = (
            session.query(UploadedFile)
            .filter(
                UploadedFile.account_id == UUID(account_id),
                UploadedFile.purpose == purpose,
                UploadedFile.filename == filename,
                UploadedFile.status == "ready",
            )
            .first()
        )
        if existing is not None:
            return existing

        object_meta = self._storage.get_object_metadata(source_key)
        if object_meta is None:
            return None

        content = self._storage.download_bytes(source_key)
        content_type = str(object_meta.get("content_type") or "").strip().lower() or _content_type_from_key(source_key)
        suffix = _suffix_for_content(content_type, source_key)
        uploaded_url = self._storage.upload_bytes(
            content,
            suffix=suffix,
            prefix=f"{account_id}/{purpose}",
        )
        uploaded_key = self._storage.extract_storage_key(uploaded_url)
        if not uploaded_key:
            return None

        uploaded_file = UploadedFile(
            account_id=UUID(account_id),
            purpose=purpose,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            storage_key=uploaded_key,
            file_url=uploaded_url,
            status="ready",
        )
        session.add(uploaded_file)
        session.commit()
        session.refresh(uploaded_file)
        return uploaded_file

    def _serialize_design_draft(self, draft: DesignDraft) -> dict:
        return self._media_urls.resolve_many(
            _serialize_design_draft(draft),
            "source_image_url",
            "style_reference_image_url",
        )


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


def _serialize_design_draft(draft: DesignDraft) -> dict:
    return {
        "id": str(draft.id),
        "status": draft.status,
        "source_file_id": str(draft.source_file_id) if draft.source_file_id else None,
        "source_image_url": draft.source_image_url,
        "style_reference_file_id": (
            str(draft.style_reference_file_id) if draft.style_reference_file_id else None
        ),
        "style_reference_image_url": draft.style_reference_image_url,
        "style_reference_enabled": draft.style_reference_enabled,
        "user_request": draft.user_request,
        "estimated_units": draft.estimated_units,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


def _content_type_from_key(storage_key: str) -> str:
    suffix = Path(storage_key).suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "image/jpeg"


def _suffix_for_content(content_type: str, storage_key: str) -> str:
    normalized = str(content_type or "").strip().lower()
    if normalized == "image/png":
        return ".png"
    if normalized == "image/webp":
        return ".webp"
    suffix = Path(storage_key).suffix.lower()
    return suffix or ".jpg"


def _result_source_filename(storage_key: str, purpose: str) -> str:
    suffix = Path(storage_key).suffix.lower() or ".jpg"
    digest = hashlib.sha1(storage_key.encode("utf-8")).hexdigest()[:12]
    return f"{purpose}-{digest}{suffix}"
