"""Support service for web support entry points."""
from __future__ import annotations

from app_services.analytics.events import EVENT_SUPPORT_REQUESTED
from app_services.analytics.service import AnalyticsService
from config import Settings


class SupportService:
    def __init__(self, settings: Settings, analytics: AnalyticsService) -> None:
        self._settings = settings
        self._analytics = analytics

    async def get_options(self) -> dict:
        return {
            "email": "owner@vizuai.example",
            "email_mailto": "mailto:owner@vizuai.example?subject=VizuAI%20support",
            "telegram_channel_url": "https://example.com/support",
            "instagram_url": "https://instagram.com/vizuai_bot",
            "refund_policy_url": f"{self._settings.WEB_PUBLIC_URL.rstrip('/')}/legal/refund-policy",
        }

    async def request_support(self, account_id: str, payload: dict) -> dict:
        reason = str(payload.get("reason") or "general").strip().lower()[:64] or "general"
        source_screen = str(payload.get("source_screen") or "unknown").strip().lower()[:64] or "unknown"
        preferred_channel = (
            str(payload.get("preferred_channel") or "email").strip().lower()[:32] or "email"
        )
        context = str(payload.get("context") or "").strip()
        await self._analytics.record_event(
            account_id,
            event_type=EVENT_SUPPORT_REQUESTED,
            screen_key=source_screen,
            action_key="support_request",
            source="web_api",
            meta={
                "reason": reason,
                "preferred_channel": preferred_channel,
                "context": context[:1000] if context else None,
            },
        )
        return {
            "status": "recorded",
            "support": await self.get_options(),
        }
