"""Analytics schemas."""
from __future__ import annotations

from pydantic import BaseModel


class AnalyticsEventRequest(BaseModel):
    event_type: str
    screen_key: str | None = None
    action_key: str | None = None
    source: str | None = None
    path: str | None = None
    referrer: str | None = None
    anon_id: str | None = None
    meta: dict[str, object] | None = None


class AnalyticsEventResponse(BaseModel):
    status: str
    anon_id: str | None = None
