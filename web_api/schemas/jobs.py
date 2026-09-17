"""Jobs schemas."""
from __future__ import annotations

from pydantic import BaseModel


class JobResponse(BaseModel):
    id: str
    status: str
