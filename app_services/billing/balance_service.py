"""Balance service for account-based web billing."""
from __future__ import annotations

from uuid import UUID

from app_services.billing.ledger import get_account_balance_snapshot
from services.db_connection import get_db_session


class BalanceService:
    async def get_balance(self, account_id: str) -> dict:
        with get_db_session() as session:
            snapshot = get_account_balance_snapshot(session, UUID(account_id))
            return {"credits": snapshot["credits"]}
