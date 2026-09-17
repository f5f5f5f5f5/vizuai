"""History service scaffold."""
from __future__ import annotations

import math
from uuid import UUID

from app_services.media_urls import MediaUrlResolver
from config import Settings
from services.db_connection import get_db_session
from services.repositories.design_repository import DesignRepository


class HistoryService:
    def __init__(self, settings: Settings) -> None:
        self._media_urls = MediaUrlResolver(settings)

    async def list_history(
        self,
        account_id: str,
        *,
        mode: str | None = None,
        status: str | None = None,
        query: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        with get_db_session() as session:
            designs, total_items = DesignRepository(session).get_account_designs_paginated(
                UUID(account_id),
                mode=mode,
                status=status,
                query=query,
                page=page,
                page_size=page_size,
            )
            total_pages = max(math.ceil(total_items / page_size), 1) if total_items else 0
            return {
                "items": [self._serialize_history_item(design) for design in designs],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_items": total_items,
                    "total_pages": total_pages,
                    "has_more": page < total_pages,
                },
                "filters": {
                    "mode": mode,
                    "status": status,
                    "query": query.strip() if query else None,
                },
            }

    async def get_item(self, account_id: str, item_id: str) -> dict | None:
        with get_db_session() as session:
            design = DesignRepository(session).get_account_design(UUID(account_id), UUID(item_id))
            if design is None:
                return None
            return self._serialize_history_item(design)

    def _serialize_history_item(self, design) -> dict:
        return self._media_urls.resolve_many(
            _serialize_history_item(design),
            "preview_image_url",
            "original_image_url",
        )


def _serialize_history_item(design) -> dict:
    return {
        "id": str(design.id),
        "mode": design.mode,
        "status": design.status,
        "title": "Поиск мебели" if design.mode == "furniture_search" else "Дизайн комнаты",
        "preview_image_url": design.final_image_url or design.render_image_url or design.original_image_url,
        "original_image_url": design.original_image_url,
        "user_request": design.user_request,
        "units_spent": design.units_spent,
        "error_message": design.error_message,
        "error_stage": design.error_stage,
        "retry_eligible": _is_retry_eligible(design),
        "created_at": design.created_at,
        "ended_at": design.ended_at,
    }


def _is_retry_eligible(design) -> bool:
    if getattr(design, "mode", None) == "furniture_search":
        job = getattr(design, "job", None)
        return bool(job and getattr(job, "draft_type", None) == "furniture_search" and getattr(job, "draft_id", None))
    draft = getattr(design, "draft", None)
    return bool(draft and getattr(draft, "source_file_id", None))
