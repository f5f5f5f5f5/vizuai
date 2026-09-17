"""Design result service scaffold."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from uuid import UUID

import aiohttp

from app_services.media_urls import MediaUrlResolver
from config import Settings
from services.db_connection import get_db_session
from services.repositories.design_repository import DesignRepository
from services.storage import S3Storage

logger = logging.getLogger("design_result_service")


class DesignResultService:
    def __init__(self, settings: Settings) -> None:
        self._media_urls = MediaUrlResolver(settings)
        self._storage = S3Storage(settings, prefix="uploads/")

    async def get_result(self, account_id: str, result_id: str) -> dict | None:
        with get_db_session() as session:
            design = DesignRepository(session).get_account_design(
                UUID(account_id),
                UUID(result_id),
            )
            if design is None or design.mode == "furniture_search":
                return None
            return self._media_urls.resolve_many({
                "id": str(design.id),
                "mode": design.mode,
                "status": design.status,
                "original_image_url": design.original_image_url,
                "prepared_image_url": design.prepared_image_url,
                "render_image_url": design.render_image_url,
                "fix_image_url": design.fix_image_url,
                "final_image_url": design.final_image_url,
                "style_reference_image_url": design.style_reference_image_url,
                "style_reference_used": bool(design.style_reference_used),
                "style_reference_status": design.style_reference_status,
                "selected_image": design.selected_image,
                "user_request": design.user_request,
                "error_message": design.error_message,
                "error_stage": design.error_stage,
                "units_spent": design.units_spent,
                "cost_usd": float(design.cost_usd) if design.cost_usd is not None else None,
                "created_at": design.created_at,
                "ended_at": design.ended_at,
                "retry_eligible": bool(design.draft and design.draft.source_file_id),
                "metadata": design.metadata_json or {},
                "debug": {
                    "degraded": bool((design.debug_json or {}).get("degraded")),
                    "degraded_reasons": (design.debug_json or {}).get("degraded_reasons") or [],
                },
            }, "original_image_url", "prepared_image_url", "render_image_url", "fix_image_url", "final_image_url", "style_reference_image_url")

    async def get_download_payload(self, account_id: str, result_id: str) -> dict | None:
        with get_db_session() as session:
            design = DesignRepository(session).get_account_design(
                UUID(account_id),
                UUID(result_id),
            )
            if design is None or design.mode == "furniture_search":
                return None

        source_url = (
            design.final_image_url
            or design.render_image_url
            or design.fix_image_url
        )
        if not source_url:
            return None

        storage_key = self._media_urls.extract_storage_key(source_url)
        if storage_key:
            try:
                metadata = await asyncio.to_thread(self._storage.get_object_metadata, storage_key)
                content_type = (
                    str((metadata or {}).get("content_type") or "").strip().lower()
                    or _content_type_from_key(storage_key)
                )
                content = await asyncio.to_thread(self._storage.download_bytes, storage_key)
                return {
                    "content": content,
                    "content_type": content_type,
                    "filename": _build_download_filename(result_id, storage_key, content_type),
                }
            except Exception as exc:
                logger.warning(
                    "design_download_storage_fallback result_id=%s key=%s error=%s",
                    result_id,
                    storage_key,
                    exc,
                )

        return await _download_by_url(source_url, result_id, "vizuai-result")


def _content_type_from_key(storage_key: str) -> str:
    suffix = Path(storage_key).suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    return "image/jpeg"


def _build_download_filename(result_id: str, storage_key: str, content_type: str) -> str:
    suffix = Path(storage_key).suffix.lower()
    if not suffix:
        if content_type == "image/png":
            suffix = ".png"
        elif content_type == "image/webp":
            suffix = ".webp"
        else:
            suffix = ".jpg"
    return f"vizuai-result-{result_id[:8]}{suffix}"


async def _download_by_url(source_url: str, result_id: str, filename_prefix: str) -> dict | None:
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(source_url) as response:
            if response.status != 200:
                return None
            content = await response.read()
            content_type = (
                str(response.headers.get("Content-Type") or "").strip().lower()
                or _content_type_from_key(source_url)
            )
            return {
                "content": content,
                "content_type": content_type,
                "filename": _build_download_filename_from_url(result_id, source_url, content_type, filename_prefix),
            }


def _build_download_filename_from_url(
    result_id: str,
    source_url: str,
    content_type: str,
    filename_prefix: str,
) -> str:
    suffix = Path(source_url.split("?", 1)[0]).suffix.lower()
    if not suffix:
        if content_type == "image/png":
            suffix = ".png"
        elif content_type == "image/webp":
            suffix = ".webp"
        else:
            suffix = ".jpg"
    return f"{filename_prefix}-{result_id[:8]}{suffix}"
