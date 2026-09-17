"""Design schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class DesignDraftCreateRequest(BaseModel):
    source_file_id: str
    user_request: str
    style_reference_file_id: str | None = None
    style_reference_enabled: bool = False
    settings_json: dict | None = None


class DesignDraftUpdateRequest(BaseModel):
    user_request: str | None = None
    style_reference_file_id: str | None = None
    style_reference_enabled: bool | None = None


class DesignJobCreateRequest(BaseModel):
    draft_id: str


class DesignDraftResponse(BaseModel):
    id: str
    status: str
    source_file_id: str | None = None
    source_image_url: str
    style_reference_file_id: str | None = None
    style_reference_image_url: str | None = None
    style_reference_enabled: bool
    user_request: str
    estimated_units: int | None = None
    created_at: datetime
    updated_at: datetime


class DesignDraftListResponse(BaseModel):
    items: list[DesignDraftResponse]


class DesignDraftSeedResponse(BaseModel):
    source_file_id: str
    source_image_url: str
    style_reference_file_id: str | None = None
    style_reference_image_url: str | None = None
    style_reference_enabled: bool = False
    user_request: str
    estimated_units: int | None = None
