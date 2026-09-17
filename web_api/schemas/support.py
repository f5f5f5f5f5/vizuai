"""Support schemas."""
from __future__ import annotations

from pydantic import BaseModel


class SupportOptionsResponse(BaseModel):
    email: str
    email_mailto: str
    telegram_channel_url: str
    instagram_url: str
    refund_policy_url: str


class SupportRequestCreateRequest(BaseModel):
    reason: str = "general"
    source_screen: str = "unknown"
    preferred_channel: str = "email"
    context: str | None = None


class SupportRequestCreateResponse(BaseModel):
    status: str
    support: SupportOptionsResponse
