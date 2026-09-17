"""Upload schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UploadIntentRequest(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    purpose: str


class UploadCompleteRequest(BaseModel):
    storage_key: str


class UploadIntentPayload(BaseModel):
    upload_id: str
    upload_url: str
    storage_key: str
    method: str
    headers: dict[str, str]
    expires_at: datetime


class UploadIntentResponse(BaseModel):
    upload: UploadIntentPayload


class UploadedFilePayload(BaseModel):
    file_id: str
    url: str
    content_type: str
    size_bytes: int


class UploadCompleteResponse(BaseModel):
    file: UploadedFilePayload
