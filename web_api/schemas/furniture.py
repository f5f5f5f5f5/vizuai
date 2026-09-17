"""Furniture schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class FurnitureDraftCreateRequest(BaseModel):
    source_file_id: str
    user_request: str | None = None
    settings_json: dict | None = None


class FurnitureDraftUpdateRequest(BaseModel):
    user_request: str | None = None


class FurnitureJobCreateRequest(BaseModel):
    draft_id: str


class FurnitureDraftResponse(BaseModel):
    id: str
    status: str
    source_file_id: str | None = None
    source_image_url: str
    user_request: str | None = None
    estimated_units: int | None = None
    created_at: datetime
    updated_at: datetime


class FurnitureDraftListResponse(BaseModel):
    items: list[FurnitureDraftResponse]


class FurnitureDraftSeedResponse(BaseModel):
    source_file_id: str
    source_image_url: str
    user_request: str | None = None
    estimated_units: int | None = None
