"""Design workflow service scaffold."""
from __future__ import annotations


class DesignWorkflowService:
    async def start_job(self, account_id: str, draft_id: str) -> dict:
        raise NotImplementedError
