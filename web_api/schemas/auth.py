"""Auth schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr


class AuthStartRequest(BaseModel):
    email: EmailStr
    locale: str | None = None


class AcquisitionContextPayload(BaseModel):
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    utm_term: str | None = None
    landing_host: str | None = None
    landing_path: str | None = None
    referrer: str | None = None


class AuthVerifyRequest(BaseModel):
    token: str
    anon_id: str | None = None
    acquisition: AcquisitionContextPayload | None = None
    locale: str | None = None


class AccountPayload(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    locale: str | None = None
    timezone: str | None = None
    created_at: datetime
    last_seen_at: datetime | None = None


class SessionPayload(BaseModel):
    expires_at: datetime


class AuthStartResponse(BaseModel):
    status: str


class AuthVerifyResponse(BaseModel):
    account: AccountPayload
    session: SessionPayload


class AuthMeResponse(BaseModel):
    account: AccountPayload
    balance: dict[str, int]
