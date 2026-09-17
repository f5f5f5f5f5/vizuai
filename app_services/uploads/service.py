"""Uploads application service scaffold."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from config import Settings
from models.upload_intent_model import UploadIntent
from models.uploaded_file_model import UploadedFile
from services.db_connection import get_db_session
from services.storage import S3Storage
from utils.time import utcnow


ALLOWED_IMAGE_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


class UploadsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._storage = S3Storage(settings, prefix="uploads/")

    async def create_intent(self, account_id: str, payload: dict) -> dict:
        return await asyncio.to_thread(self._create_intent_sync, account_id, payload)

    async def complete_intent(self, account_id: str, upload_id: str, storage_key: str) -> dict:
        return await asyncio.to_thread(self._complete_intent_sync, account_id, upload_id, storage_key)

    def _create_intent_sync(self, account_id: str, payload: dict) -> dict:
        content_type = str(payload.get("content_type") or "").strip().lower()
        filename = str(payload.get("filename") or "").strip() or "upload.bin"
        purpose = str(payload.get("purpose") or "").strip().lower()
        size_bytes = int(payload.get("size_bytes") or 0)
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            return {"status": "invalid_content_type"}
        if size_bytes <= 0 or size_bytes > int(self._settings.WEB_MAX_UPLOAD_SIZE_BYTES):
            return {"status": "invalid_size"}

        suffix = Path(filename).suffix.lower() or _suffix_for_content_type(content_type)
        expires_at = utcnow() + timedelta(minutes=max(int(self._settings.WEB_UPLOAD_INTENT_TTL_MINUTES), 1))
        key, upload_url = self._storage.create_signed_upload_url(
            content_type=content_type,
            suffix=suffix,
            prefix=f"uploads/{account_id}/{purpose}",
            expires_in=max(int(self._settings.WEB_UPLOAD_INTENT_TTL_MINUTES), 1) * 60,
        )

        with get_db_session() as session:
            intent = UploadIntent(
                account_id=UUID(account_id),
                purpose=purpose,
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                storage_key=key,
                status="pending",
                expires_at=expires_at,
            )
            session.add(intent)
            session.commit()
            session.refresh(intent)
            return {
                "status": "ok",
                "upload": {
                    "upload_id": str(intent.id),
                    "upload_url": upload_url,
                    "storage_key": key,
                    "method": "PUT",
                    "headers": {"Content-Type": content_type},
                    "expires_at": expires_at,
                },
            }

    def _complete_intent_sync(self, account_id: str, upload_id: str, storage_key: str) -> dict:
        with get_db_session() as session:
            intent = (
                session.query(UploadIntent)
                .filter(
                    UploadIntent.id == UUID(upload_id),
                    UploadIntent.account_id == UUID(account_id),
                )
                .first()
            )
            if intent is None:
                return {"status": "not_found"}
            if intent.status != "pending":
                return {"status": "conflict"}
            if intent.expires_at <= utcnow():
                intent.status = "expired"
                session.commit()
                return {"status": "expired"}
            if storage_key != intent.storage_key:
                return {"status": "storage_key_mismatch"}
            object_meta = self._storage.get_object_metadata(storage_key)
            if object_meta is None:
                return {"status": "storage_object_missing"}
            if int(object_meta.get("size_bytes") or 0) != int(intent.size_bytes or 0):
                return {
                    "status": "storage_size_mismatch",
                    "expected_size_bytes": int(intent.size_bytes or 0),
                    "actual_size_bytes": int(object_meta.get("size_bytes") or 0),
                }
            object_content_type = str(object_meta.get("content_type") or "").strip().lower()
            if object_content_type and object_content_type != str(intent.content_type or "").strip().lower():
                return {
                    "status": "storage_content_type_mismatch",
                    "expected_content_type": str(intent.content_type or "").strip().lower(),
                    "actual_content_type": object_content_type,
                }

            file_url = self._storage.get_object_url(storage_key)
            uploaded_file = UploadedFile(
                account_id=intent.account_id,
                purpose=intent.purpose,
                filename=intent.filename,
                content_type=intent.content_type,
                size_bytes=intent.size_bytes,
                storage_key=intent.storage_key,
                file_url=file_url,
                status="ready",
            )
            session.add(uploaded_file)
            session.flush()
            intent.status = "completed"
            intent.completed_at = utcnow()
            intent.file_id = uploaded_file.id
            session.commit()
            session.refresh(uploaded_file)
            return {
                "status": "ok",
                "file": {
                    "file_id": str(uploaded_file.id),
                    "url": uploaded_file.file_url,
                    "content_type": uploaded_file.content_type,
                    "size_bytes": uploaded_file.size_bytes,
                },
            }


def _suffix_for_content_type(content_type: str) -> str:
    if content_type == "image/png":
        return ".png"
    if content_type == "image/webp":
        return ".webp"
    return ".jpg"
