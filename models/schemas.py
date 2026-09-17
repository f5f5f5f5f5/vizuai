"""Pydantic models for pipeline data."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from utils.time import utcnow


class VisionVertex(BaseModel):
    """Normalized vertex from Google Vision (0..1)."""

    x: float
    y: float


class VisionObject(BaseModel):
    """Detected object metadata used in the pipeline."""

    label: str
    score: float = Field(..., ge=0.0, le=1.0)
    area: float = Field(..., ge=0.0, le=1.0)
    bounding_box: list[VisionVertex]
    crop_key: str | None = None


class ProductResult(BaseModel):
    """Matched product data from marketplace search."""

    label: str
    url: str
    source: str = "ozon"
    price: float | None = None
    currency: str | None = None


class Job(BaseModel):
    """Aggregated job state for the pipeline."""

    job_id: str
    chat_id: int
    created_at: datetime = Field(default_factory=utcnow)
    status: str = "pending"
    mode: str = "render_only"
    units_spent: int = 0
    account_id: str | None = None
    draft_id: str | None = None
    user_prompt: str | None = None
    render_prompt: str | None = None
    input_image_key: str | None = None
    render_image_key: str | None = None
    render_mask_info: str | None = None
    vision_objects: list[VisionObject] = Field(default_factory=list)
    product_results: list[ProductResult] = Field(default_factory=list)
    costs: dict[str, float] = Field(default_factory=dict)
    debug: dict[str, Any] = Field(default_factory=dict)
