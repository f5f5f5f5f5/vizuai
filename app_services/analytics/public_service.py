"""Analytics service for anonymous public-site events."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from models.public_site_event_model import PublicSiteEvent
from services.db_connection import get_db_session
from app_services.analytics.acquisition_service import upsert_web_acquisition_touch


class PublicAnalyticsService:
    async def record_event(
        self,
        *,
        anon_id: str | None = None,
        event_type: str,
        screen_key: str | None = None,
        action_key: str | None = None,
        source: str | None = None,
        path: str | None = None,
        referrer: str | None = None,
        host: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> str:
        return await asyncio.to_thread(
            self._record_event_sync,
            anon_id=anon_id,
            event_type=event_type,
            screen_key=screen_key,
            action_key=action_key,
            source=source,
            path=path,
            referrer=referrer,
            host=host,
            meta=meta,
        )

    def _record_event_sync(
        self,
        *,
        anon_id: str | None = None,
        event_type: str,
        screen_key: str | None = None,
        action_key: str | None = None,
        source: str | None = None,
        path: str | None = None,
        referrer: str | None = None,
        host: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> str:
        resolved_anon_id = (str(anon_id).strip()[:64] if anon_id else None) or str(uuid4())
        with get_db_session() as session:
            event = PublicSiteEvent(
                anon_id=resolved_anon_id,
                event_type=str(event_type or "")[:32],
                screen_key=(str(screen_key)[:64] if screen_key else None),
                action_key=(str(action_key)[:128] if action_key else None),
                source=(str(source)[:64] if source else None),
                path=(str(path)[:255] if path else None),
                referrer=(str(referrer)[:255] if referrer else None),
                meta_json=(json.dumps(meta, ensure_ascii=True) if isinstance(meta, dict) else None),
            )
            session.add(event)
            upsert_web_acquisition_touch(
                session,
                anon_id=resolved_anon_id,
                path=path,
                referrer=referrer,
                host=host,
                acquisition=meta,
            )
            session.commit()
        return resolved_anon_id
