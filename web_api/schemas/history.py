"""History schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HistoryItemResponse(BaseModel):
    id: str
    mode: str
    status: str
    title: str | None = None
    preview_image_url: str | None = None
    original_image_url: str | None = None
    user_request: str | None = None
    units_spent: int | None = None
    error_message: str | None = None
    error_stage: str | None = None
    retry_eligible: bool = False
    created_at: datetime
    ended_at: datetime | None = None


class HistoryPaginationResponse(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_more: bool


class HistoryFiltersResponse(BaseModel):
    mode: str | None = None
    status: str | None = None
    query: str | None = None


class HistoryListResponse(BaseModel):
    items: list[HistoryItemResponse]
    pagination: HistoryPaginationResponse
    filters: HistoryFiltersResponse
