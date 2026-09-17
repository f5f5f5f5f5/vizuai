"""Account schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AccountUpdateRequest(BaseModel):
    display_name: str | None = None
    locale: str | None = None
    timezone: str | None = None


class AccountPayload(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    locale: str | None = None
    timezone: str | None = None
    marketing_opt_in: bool = False
    created_at: datetime
    last_seen_at: datetime | None = None


class AccountUsagePayload(BaseModel):
    total_runs: int
    completed_runs: int
    failed_runs: int
    design_runs: int
    furniture_runs: int
    credits_spent: int
