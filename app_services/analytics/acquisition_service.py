"""Durable first-touch acquisition attribution for web visitors."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import timedelta
from uuid import UUID, uuid4

from models.account_flow_event_model import AccountFlowEvent
from models.web_acquisition_attribution_model import WebAcquisitionAttribution
from services.db_connection import get_db_session
from utils.time import utcnow


def _clean_string(value: object | None, max_length: int) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:max_length]


def _normalize_anon_id(anon_id: str | None) -> str:
    cleaned = _clean_string(anon_id, 64)
    return cleaned or str(uuid4())


def _normalize_acquisition(acquisition: dict[str, object] | None) -> dict[str, str | None]:
    payload = acquisition if isinstance(acquisition, dict) else {}
    nested = payload.get("acquisition")
    source_payload = nested if isinstance(nested, dict) else payload
    return {
        "utm_source": _clean_string(source_payload.get("utm_source"), 255),
        "utm_medium": _clean_string(source_payload.get("utm_medium"), 255),
        "utm_campaign": _clean_string(source_payload.get("utm_campaign"), 255),
        "utm_content": _clean_string(source_payload.get("utm_content"), 255),
        "utm_term": _clean_string(source_payload.get("utm_term"), 255),
        "landing_host": _clean_string(source_payload.get("landing_host"), 255),
        "landing_path": _clean_string(source_payload.get("landing_path"), 255),
        "referrer": _clean_string(source_payload.get("referrer"), 1024),
    }


def upsert_web_acquisition_touch(
    session,
    *,
    anon_id: str | None,
    path: str | None = None,
    referrer: str | None = None,
    host: str | None = None,
    acquisition: dict[str, object] | None = None,
) -> WebAcquisitionAttribution:
    resolved_anon_id = _normalize_anon_id(anon_id)
    now = utcnow()
    normalized = _normalize_acquisition(acquisition)
    row = (
        session.query(WebAcquisitionAttribution)
        .filter(WebAcquisitionAttribution.anon_id == resolved_anon_id)
        .with_for_update()
        .first()
    )
    if row is None:
        row = WebAcquisitionAttribution(
            anon_id=resolved_anon_id,
            first_utm_source=normalized["utm_source"],
            first_utm_medium=normalized["utm_medium"],
            first_utm_campaign=normalized["utm_campaign"],
            first_utm_content=normalized["utm_content"],
            first_utm_term=normalized["utm_term"],
            first_landing_host=normalized["landing_host"] or _clean_string(host, 255),
            first_landing_path=_clean_string(path, 255) or normalized["landing_path"],
            first_referrer=_clean_string(referrer, 1024) or normalized["referrer"],
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(row)
        session.flush()
        return row

    row.last_seen_at = now
    return row


def bind_web_acquisition_to_account(
    session,
    *,
    account_id: UUID,
    anon_id: str | None,
    acquisition: dict[str, object] | None = None,
) -> WebAcquisitionAttribution | None:
    if not anon_id:
        return None
    row = upsert_web_acquisition_touch(session, anon_id=anon_id, acquisition=acquisition)
    if row.account_id is None or row.account_id == account_id:
        row.account_id = account_id
        row.linked_at = row.linked_at or utcnow()
    return row


class AcquisitionService:
    async def bind_account(
        self,
        *,
        account_id: str,
        anon_id: str | None,
        acquisition: dict[str, object] | None = None,
    ) -> None:
        if not anon_id:
            return
        await asyncio.to_thread(
            self._bind_account_sync,
            account_id=account_id,
            anon_id=anon_id,
            acquisition=acquisition,
        )

    def _bind_account_sync(
        self,
        *,
        account_id: str,
        anon_id: str | None,
        acquisition: dict[str, object] | None = None,
    ) -> None:
        with get_db_session() as session:
            bind_web_acquisition_to_account(
                session,
                account_id=UUID(account_id),
                anon_id=anon_id,
                acquisition=acquisition,
            )
            session.commit()

    async def build_report(self, *, days: int = 30) -> dict[str, object]:
        return await asyncio.to_thread(self._build_report_sync, days=max(int(days or 30), 1))

    def _build_report_sync(self, *, days: int) -> dict[str, object]:
        cutoff = utcnow() - timedelta(days=days)
        tracked_events = {
            "auth_verified",
            "checkout_created",
            "checkout_paid",
            "design_job_created",
            "furniture_job_created",
        }
        with get_db_session() as session:
            attributions = (
                session.query(WebAcquisitionAttribution)
                .filter(WebAcquisitionAttribution.first_seen_at >= cutoff)
                .order_by(WebAcquisitionAttribution.first_seen_at.asc())
                .all()
            )
            account_ids = sorted({row.account_id for row in attributions if row.account_id is not None}, key=str)
            events_by_account: dict[UUID, list[AccountFlowEvent]] = defaultdict(list)
            if account_ids:
                events = (
                    session.query(AccountFlowEvent)
                    .filter(
                        AccountFlowEvent.account_id.in_(account_ids),
                        AccountFlowEvent.event_type.in_(tracked_events),
                        AccountFlowEvent.created_at >= cutoff,
                    )
                    .all()
                )
                for event in events:
                    events_by_account[event.account_id].append(event)

        sources: dict[tuple[str, str, str, str, str], dict[str, object]] = {}
        totals = {
            "visitors": 0,
            "logins": 0,
            "checkout_started": 0,
            "checkout_paid": 0,
            "jobs_launched": 0,
        }

        for row in attributions:
            group_key = (
                row.first_utm_source or "(direct)",
                row.first_utm_medium or "(none)",
                row.first_utm_campaign or "(none)",
                row.first_utm_content or "(none)",
                row.first_utm_term or "(none)",
            )
            bucket = sources.setdefault(
                group_key,
                {
                    "utm_source": group_key[0],
                    "utm_medium": group_key[1],
                    "utm_campaign": group_key[2],
                    "utm_content": group_key[3],
                    "utm_term": group_key[4],
                    "visitors": 0,
                    "logins": 0,
                    "checkout_started": 0,
                    "checkout_paid": 0,
                    "jobs_launched": 0,
                },
            )
            bucket["visitors"] += 1
            totals["visitors"] += 1

            if row.account_id is None:
                continue

            threshold = row.linked_at or row.first_seen_at
            events = [event for event in events_by_account.get(row.account_id, []) if event.created_at >= threshold]
            event_types = {event.event_type for event in events}

            bucket["logins"] += 1
            totals["logins"] += 1

            if "checkout_created" in event_types:
                bucket["checkout_started"] += 1
                totals["checkout_started"] += 1
            if "checkout_paid" in event_types:
                bucket["checkout_paid"] += 1
                totals["checkout_paid"] += 1
            if {"design_job_created", "furniture_job_created"} & event_types:
                bucket["jobs_launched"] += 1
                totals["jobs_launched"] += 1

        ordered_sources = sorted(
            sources.values(),
            key=lambda item: (
                -int(item["visitors"]),
                str(item["utm_source"]),
                str(item["utm_campaign"]),
            ),
        )
        return {
            "days": days,
            "generated_at": utcnow().isoformat(),
            "totals": totals,
            "sources": ordered_sources,
        }
