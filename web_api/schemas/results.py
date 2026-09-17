"""Result response schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DesignResultResponse(BaseModel):
    id: str
    mode: str
    status: str
    original_image_url: str
    prepared_image_url: str | None = None
    render_image_url: str | None = None
    fix_image_url: str | None = None
    final_image_url: str | None = None
    style_reference_image_url: str | None = None
    style_reference_used: bool
    style_reference_status: str | None = None
    selected_image: str | None = None
    user_request: str
    error_message: str | None = None
    error_stage: str | None = None
    units_spent: int | None = None
    cost_usd: float | None = None
    created_at: datetime
    ended_at: datetime | None = None
    retry_eligible: bool = False
    metadata: dict
    debug: dict


class FurnitureResultResponse(BaseModel):
    id: str
    mode: str
    status: str
    original_image_url: str
    final_image_url: str | None = None
    user_request: str
    error_message: str | None = None
    error_stage: str | None = None
    units_spent: int | None = None
    created_at: datetime
    ended_at: datetime | None = None
    retry_eligible: bool = False
    summary_text: str | None = None
    object_cards: list[dict]
    products_count: int
    metadata: dict
