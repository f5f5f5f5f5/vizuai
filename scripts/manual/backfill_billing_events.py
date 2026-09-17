#!/usr/bin/env python3
"""Backfill missing billing_events from payments statuses.

Usage:
  PYTHONPATH=. python3 scripts/manual/backfill_billing_events.py --provider telegram_stars --apply
  PYTHONPATH=. python3 scripts/manual/backfill_billing_events.py --provider tbank_sbp --dry-run
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from models.billing_event_model import BillingEvent
from models.payment_model import Payment
from services.db_connection import get_db_session
from utils.time import utcnow


@dataclass(frozen=True)
class ProviderMap:
    paid_event: str
    refunded_event: str
    amount_as_kopecks: bool


PROVIDERS: dict[str, ProviderMap] = {
    "telegram_stars": ProviderMap(
        paid_event="stars_payment_paid",
        refunded_event="stars_refund_applied",
        amount_as_kopecks=False,
    ),
    "tbank_sbp": ProviderMap(
        paid_event="tbank_payment_paid",
        refunded_event="tbank_payment_refunded",
        amount_as_kopecks=True,
    ),
}


def _amount_for_event(payment: Payment, *, as_kopecks: bool) -> int:
    value = Decimal(payment.price_final or 0)
    if as_kopecks:
        return int((value * Decimal("100")).quantize(Decimal("1")))
    return int(value)


def _event_exists(
    *,
    payment_id,
    provider: str,
    event_type: str,
) -> bool:
    with get_db_session() as session:
        row = (
            session.query(BillingEvent.id)
            .filter(
                BillingEvent.provider == provider,
                BillingEvent.event_type == event_type,
                BillingEvent.payment_id == payment_id,
            )
            .first()
        )
        return row is not None


def _insert_event(
    *,
    payment: Payment,
    provider: str,
    event_type: str,
    created_at: datetime,
    amount_as_kopecks: bool,
    reason: str,
) -> None:
    with get_db_session() as session:
        event = BillingEvent(
            provider=provider,
            event_type=event_type,
            user_id=int(payment.user_id),
            payment_id=payment.id,
            provider_payment_id=payment.provider_payment_id,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            currency=payment.currency,
            stars_amount=_amount_for_event(payment, as_kopecks=amount_as_kopecks),
            credits_amount=int(payment.credits_amount or 0),
            reason=reason,
            meta_json='{"backfill": true}',
            created_at=created_at,
        )
        session.add(event)
        session.commit()


def run(provider: str, apply: bool) -> None:
    mapping = PROVIDERS[provider]
    now = utcnow()
    added = 0
    checked = 0
    with get_db_session() as session:
        payments = (
            session.query(Payment)
            .filter(
                Payment.provider == provider,
                Payment.status.in_(("paid", "refunded")),
            )
            .order_by(Payment.created_at.asc())
            .all()
        )

    for payment in payments:
        checked += 1
        if payment.status == "paid":
            if not _event_exists(payment_id=payment.id, provider=provider, event_type=mapping.paid_event):
                if apply:
                    _insert_event(
                        payment=payment,
                        provider=provider,
                        event_type=mapping.paid_event,
                        created_at=payment.paid_at or payment.created_at or now,
                        amount_as_kopecks=mapping.amount_as_kopecks,
                        reason="backfill_paid",
                    )
                added += 1
        if payment.status == "refunded":
            if not _event_exists(payment_id=payment.id, provider=provider, event_type=mapping.refunded_event):
                if apply:
                    _insert_event(
                        payment=payment,
                        provider=provider,
                        event_type=mapping.refunded_event,
                        created_at=payment.refunded_at or payment.paid_at or payment.created_at or now,
                        amount_as_kopecks=mapping.amount_as_kopecks,
                        reason="backfill_refunded",
                    )
                added += 1

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[{mode}] provider={provider} checked_payments={checked} missing_events={added}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDERS.keys()),
        default="telegram_stars",
        help="Which payment provider to backfill",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually insert missing events (default is dry-run)",
    )
    args = parser.parse_args()
    run(provider=args.provider, apply=bool(args.apply))


if __name__ == "__main__":
    main()
