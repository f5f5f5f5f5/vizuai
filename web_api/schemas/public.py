"""Public content schemas."""
from __future__ import annotations

from pydantic import BaseModel


class PublicCard(BaseModel):
    id: str
    title: str
    summary: str
