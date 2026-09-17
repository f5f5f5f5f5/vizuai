"""Analytics service for account-level web flow events."""
from __future__ import annotations

import asyncio
import json
from uuid import UUID

from app_services.analytics.acquisition_service import bind_web_acquisition_to_account
from models.account_flow_event_model import AccountFlowEvent
from services.db_connection import get_db_session


class AnalyticsService:
    async def record_event(
        self,
        account_id: str,
        *,
        event_type: str,
        screen_key: str | None = None,
        action_key: str | None = None,
        source: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_event_sync,
            account_id,
            event_type=event_type,
            screen_key=screen_key,
            action_key=action_key,
            source=source,
            meta=meta,
        )

    def _record_event_sync(
        self,
        account_id: str,
        *,
        event_type: str,
        screen_key: str | None = None,
        action_key: str | None = None,
        source: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        with get_db_session() as session:
            anon_id = None
            acquisition = None
            if isinstance(meta, dict):
                raw_anon_id = meta.get("anon_id")
                anon_id = str(raw_anon_id).strip()[:64] if raw_anon_id else None
                raw_acquisition = meta.get("acquisition")
                acquisition = raw_acquisition if isinstance(raw_acquisition, dict) else None

            if anon_id:
                bind_web_acquisition_to_account(
                    session,
                    account_id=UUID(account_id),
                    anon_id=anon_id,
                    acquisition=acquisition,
                )
            append_flow_event(
                session,
                account_id=UUID(account_id),
                event_type=event_type,
                screen_key=screen_key,
                action_key=action_key,
                source=source,
                meta=meta,
            )
            session.commit()


def append_flow_event(
    session,
    *,
    account_id: UUID,
    event_type: str,
    screen_key: str | None = None,
    action_key: str | None = None,
    source: str | None = None,
    meta: dict[str, object] | None = None,
) -> AccountFlowEvent:
    event = AccountFlowEvent(
        account_id=account_id,
        event_type=str(event_type or "")[:32],
        screen_key=(str(screen_key)[:64] if screen_key else None),
        action_key=(str(action_key)[:128] if action_key else None),
        source=(str(source)[:64] if source else None),
        meta_json=(json.dumps(meta, ensure_ascii=True) if isinstance(meta, dict) else None),
    )
    session.add(event)
    return event
