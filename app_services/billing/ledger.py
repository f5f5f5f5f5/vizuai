"""Shared ledger helpers for account-based web billing."""
from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.account_model import Account
from models.billing_event_model import BillingEvent
from models.payment_model import Payment

BILLING_PROVIDER_TBANK = "tbank_sbp"
BILLING_PROVIDER_WEB = "web_app"
BILLING_EVENT_CREDITS_SPENT = "credits_spent"

DEFAULT_TBANK_PACKAGE_CATALOG_RUB = {
    1: Decimal("199"),
    3: Decimal("549"),
    10: Decimal("1599"),
}


def parse_tbank_package_catalog(raw: str | None) -> dict[int, Decimal]:
    if not raw:
        return dict(DEFAULT_TBANK_PACKAGE_CATALOG_RUB)
    try:
        import json as _json

        data = _json.loads(raw)
    except Exception:
        return dict(DEFAULT_TBANK_PACKAGE_CATALOG_RUB)
    if not isinstance(data, dict):
        return dict(DEFAULT_TBANK_PACKAGE_CATALOG_RUB)
    parsed: dict[int, Decimal] = {}
    for key, value in data.items():
        try:
            credits = int(key)
            amount = Decimal(str(value))
        except Exception:
            continue
        if credits <= 0 or amount <= 0:
            continue
        parsed[credits] = amount.quantize(Decimal("0.01"))
    if not parsed:
        return dict(DEFAULT_TBANK_PACKAGE_CATALOG_RUB)
    return parsed


def get_account_balance_snapshot(session: Session, account_id: UUID) -> dict[str, int]:
    paid_credits = (
        session.query(func.coalesce(func.sum(Payment.credits_amount), 0))
        .filter(
            Payment.account_id == account_id,
            Payment.status == "paid",
        )
        .scalar()
    )
    spent_credits = (
        session.query(func.coalesce(func.sum(BillingEvent.credits_amount), 0))
        .filter(
            BillingEvent.account_id == account_id,
            BillingEvent.event_type == BILLING_EVENT_CREDITS_SPENT,
        )
        .scalar()
    )
    total_paid = max(int(paid_credits or 0), 0)
    total_spent = max(int(spent_credits or 0), 0)
    available = max(total_paid - total_spent, 0)
    return {
        "credits": available,
        "paid_credits": total_paid,
        "spent_credits": total_spent,
    }


def reserve_account_credits(
    session: Session,
    *,
    account_id: UUID,
    units: int,
    reason: str,
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    units_to_reserve = int(units or 0)
    if units_to_reserve < 0:
        return {"status": "invalid_units"}

    account = (
        session.query(Account)
        .filter(Account.id == account_id)
        .with_for_update()
        .first()
    )
    if account is None:
        return {"status": "account_not_found"}

    snapshot = get_account_balance_snapshot(session, account_id)
    if units_to_reserve == 0:
        return {
            "status": "ok",
            "balance_before": snapshot["credits"],
            "balance_after": snapshot["credits"],
            "billing_event_id": None,
        }
    if snapshot["credits"] < units_to_reserve:
        return {
            "status": "insufficient_credits",
            "balance_before": snapshot["credits"],
            "balance_after": snapshot["credits"],
        }

    event = BillingEvent(
        provider=BILLING_PROVIDER_WEB,
        event_type=BILLING_EVENT_CREDITS_SPENT,
        account_id=account_id,
        credits_amount=units_to_reserve,
        reason=str(reason or "job_start")[:128] or None,
        meta_json=(json.dumps(meta, ensure_ascii=True) if isinstance(meta, dict) else None),
    )
    session.add(event)
    session.flush()
    return {
        "status": "ok",
        "balance_before": snapshot["credits"],
        "balance_after": snapshot["credits"] - units_to_reserve,
        "billing_event_id": str(event.id),
    }


def release_account_credit_reservation(
    session: Session,
    *,
    account_id: UUID,
    units: int,
    reason: str,
    meta: dict[str, object] | None = None,
) -> dict[str, object]:
    units_to_release = int(units or 0)
    if units_to_release <= 0:
        snapshot = get_account_balance_snapshot(session, account_id)
        return {
            "status": "ok",
            "balance_before": snapshot["credits"],
            "balance_after": snapshot["credits"],
            "billing_event_id": None,
        }

    account = (
        session.query(Account)
        .filter(Account.id == account_id)
        .with_for_update()
        .first()
    )
    if account is None:
        return {"status": "account_not_found"}

    snapshot = get_account_balance_snapshot(session, account_id)
    event = BillingEvent(
        provider=BILLING_PROVIDER_WEB,
        event_type=BILLING_EVENT_CREDITS_SPENT,
        account_id=account_id,
        credits_amount=-units_to_release,
        reason=str(reason or "job_release")[:128] or None,
        meta_json=(json.dumps(meta, ensure_ascii=True) if isinstance(meta, dict) else None),
    )
    session.add(event)
    session.flush()
    return {
        "status": "ok",
        "balance_before": snapshot["credits"],
        "balance_after": snapshot["credits"] + units_to_release,
        "billing_event_id": str(event.id),
    }
