"""Checkout service for account-based web billing."""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import func

from app_services.analytics.events import EVENT_CHECKOUT_PAID, EVENT_CHECKOUT_REFUNDED
from app_services.analytics.service import append_flow_event
from app_services.billing.ledger import (
    BILLING_PROVIDER_TBANK,
    get_account_balance_snapshot,
    parse_tbank_package_catalog,
)
from config import Settings
from models.billing_event_model import BillingEvent
from models.checkout_session_model import CheckoutSession
from models.payment_model import Payment
from models.promocode_model import Promocode
from models.promocode_usage_model import PromocodeUsage
from services.db_connection import get_db_session
from services.tbank_acquiring import TBankAcquiringService
from utils.observability import emit_observability_event
from utils.time import utcnow

logger = logging.getLogger("web_billing")

REFUND_LIKE_TBANK_STATUSES = {"REFUNDED", "REVERSED", "CANCELED"}
PENDING_CHECKOUT_STATUSES = {"pending", "invoice_sent", "authorized", "confirmed"}

PROMO_USAGE_STATUS_RESERVED = "reserved"
PROMO_USAGE_STATUS_REDEEMED = "redeemed"
PROMO_USAGE_STATUS_RELEASED = "released"
PROMO_USAGE_STATUS_EXPIRED = "expired"


class CheckoutService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tbank = TBankAcquiringService(settings)

    async def list_plans(self) -> list[dict]:
        catalog = parse_tbank_package_catalog(self._settings.WEB_TBANK_PACKAGE_CATALOG_RUB_JSON)
        return [
            {
                "provider": BILLING_PROVIDER_TBANK,
                "credits": credits,
                "currency": "RUB",
                "amount": str(amount.quantize(Decimal("0.01"))),
            }
            for credits, amount in sorted(catalog.items())
        ]

    async def preview_promocode(self, account_id: str, payload: dict) -> dict:
        provider = str(payload.get("provider") or BILLING_PROVIDER_TBANK).strip().lower()
        credits = int(payload.get("credits") or 0)
        promocode = str(payload.get("promocode") or "").strip()
        if provider != BILLING_PROVIDER_TBANK:
            return {"status": "unsupported_provider"}
        amount_rub = self._get_catalog_amount(provider, credits)
        if credits <= 0 or amount_rub is None:
            return {"status": "invalid_plan"}
        account_uuid = UUID(account_id)
        with get_db_session() as session:
            result = self._evaluate_promocode(
                session=session,
                account_id=account_uuid,
                code=promocode,
                credits=credits,
                amount_rub=amount_rub,
            )
            if result.get("status") != "ok":
                return result
            return self._serialize_promocode_preview(result)

    async def create_checkout(self, account_id: str, payload: dict) -> dict:
        provider = str(payload.get("provider") or BILLING_PROVIDER_TBANK).strip().lower()
        credits = int(payload.get("credits") or 0)
        promocode = str(payload.get("promocode") or "").strip()
        if provider != BILLING_PROVIDER_TBANK:
            emit_observability_event(
                logger,
                "billing_checkout_rejected",
                level="warning",
                reason="unsupported_provider",
                account_id=account_id,
                provider=provider,
                credits=credits,
            )
            return {"status": "unsupported_provider"}
        amount_rub = self._get_catalog_amount(provider, credits)
        if credits <= 0 or amount_rub is None:
            emit_observability_event(
                logger,
                "billing_checkout_rejected",
                level="warning",
                reason="invalid_plan",
                account_id=account_id,
                provider=provider,
                credits=credits,
            )
            return {"status": "invalid_plan"}

        created = self._create_checkout_rows(account_id, credits, amount_rub, promocode)
        if created.get("status") != "ok":
            return created
        checkout_id = str(created["checkout_id"])
        payment_id = str(created["payment_id"])
        final_amount = Decimal(str(created["amount_final"]))
        description = f"Пакет запросов VizuAI: {credits} запросов"
        success_url = self._build_return_url(checkout_id, outcome="success")
        fail_url = self._build_return_url(checkout_id, outcome="fail")
        try:
            init_result = await self._tbank.init_payment(
                order_id=payment_id,
                amount_rub=final_amount,
                description=description,
                customer_key=account_id,
                success_url=success_url,
                fail_url=fail_url,
            )
        except Exception as exc:
            logger.exception("web_checkout_init_failed checkout_id=%s payment_id=%s", checkout_id, payment_id)
            emit_observability_event(
                logger,
                "billing_checkout_init_failed",
                level="error",
                account_id=account_id,
                checkout_id=checkout_id,
                payment_id=payment_id,
                credits=credits,
                error_message=str(exc),
                exc_info=exc,
            )
            self._mark_checkout_init_failed(checkout_id, payment_id, str(exc))
            return {"status": "init_failed", "message": str(exc)}

        self._mark_checkout_initialized(
            checkout_id=checkout_id,
            payment_id=payment_id,
            provider_payment_id=init_result.payment_id,
            checkout_url=init_result.payment_url,
            provider_status=init_result.status,
            provider_raw=init_result.raw,
        )
        return await self.get_checkout(account_id, checkout_id)

    def _build_return_url(self, checkout_id: str, *, outcome: str) -> str:
        query = urlencode({"checkout": checkout_id, "return": outcome})
        return f"{self._settings.WEB_APP_URL.rstrip('/')}/app/billing?{query}"

    async def get_checkout(self, account_id: str, checkout_id: str) -> dict | None:
        snapshot = self._get_checkout_snapshot(account_id, checkout_id)
        if snapshot is None:
            return None
        payment = snapshot.get("payment")
        if (
            snapshot["provider"] == BILLING_PROVIDER_TBANK
            and snapshot["status"] in PENDING_CHECKOUT_STATUSES
            and payment is not None
            and payment.get("provider_payment_id")
            and self._tbank.is_configured()
        ):
            try:
                state = await self._tbank.get_state(payment_id=payment["provider_payment_id"])
                amount_kopecks = None
                if isinstance(state.get("raw"), dict):
                    raw_amount = state["raw"].get("Amount")
                    if raw_amount is not None:
                        try:
                            amount_kopecks = int(raw_amount)
                        except Exception:
                            amount_kopecks = None
                await self.apply_tbank_notification(
                    order_id=payment["id"],
                    provider_payment_id=state.get("payment_id"),
                    status=state.get("status"),
                    success=bool(state.get("success")),
                    amount_kopecks=amount_kopecks,
                    payload=state.get("raw") if isinstance(state.get("raw"), dict) else None,
                    accept_statuses=self._tbank.accepted_statuses(),
                )
                snapshot = self._get_checkout_snapshot(account_id, checkout_id)
            except Exception:
                logger.exception("web_checkout_state_refresh_failed checkout_id=%s", checkout_id)
                emit_observability_event(
                    logger,
                    "billing_checkout_state_refresh_failed",
                    level="warning",
                    account_id=account_id,
                    checkout_id=checkout_id,
                )
        return snapshot

    async def list_payments(self, account_id: str) -> list[dict]:
        with get_db_session() as session:
            payments = (
                session.query(Payment)
                .filter(
                    Payment.account_id == UUID(account_id),
                    Payment.status == "paid",
                )
                .order_by(Payment.paid_at.desc(), Payment.created_at.desc())
                .all()
            )
            return [_serialize_payment(payment) for payment in payments]

    async def get_payment(self, account_id: str, payment_id: str) -> dict | None:
        try:
            account_uuid = UUID(account_id)
            payment_uuid = UUID(payment_id)
        except Exception:
            return None
        with get_db_session() as session:
            payment = (
                session.query(Payment)
                .filter(
                    Payment.id == payment_uuid,
                    Payment.account_id == account_uuid,
                )
                .first()
            )
            if payment is None:
                return None
            return _serialize_payment(payment)

    async def apply_tbank_notification(
        self,
        *,
        order_id: str,
        provider_payment_id: str | None,
        status: str | None,
        success: bool,
        amount_kopecks: int | None,
        payload: dict[str, object] | None,
        accept_statuses: set[str] | None,
    ) -> dict:
        return self._apply_tbank_notification_sync(
            order_id=order_id,
            provider_payment_id=provider_payment_id,
            status=status,
            success=success,
            amount_kopecks=amount_kopecks,
            payload=payload,
            accept_statuses=accept_statuses,
        )

    def _create_checkout_rows(
        self,
        account_id: str,
        credits: int,
        amount_rub: Decimal,
        promocode: str,
    ) -> dict:
        account_uuid = UUID(account_id)
        with get_db_session() as session:
            promo_result = None
            if promocode:
                promo_result = self._reserve_promocode_for_checkout(
                    session=session,
                    account_id=account_uuid,
                    code=promocode,
                    credits=credits,
                    amount_rub=amount_rub,
                )
                if promo_result.get("status") != "ok":
                    session.rollback()
                    return {
                        "status": "invalid_promocode",
                        "reason": promo_result.get("reason"),
                    }

            discount_amount = (
                promo_result["discount_amount_decimal"] if promo_result is not None else Decimal("0.00")
            )
            amount_final = promo_result["amount_final_decimal"] if promo_result is not None else amount_rub
            metadata_json = None
            if promo_result is not None:
                metadata_json = {
                    "promocode": {
                        "code": promo_result["code"],
                        "discount_type": promo_result["discount_type"],
                        "discount_value": promo_result["discount_value"],
                    }
                }

            checkout = CheckoutSession(
                account_id=account_uuid,
                provider=BILLING_PROVIDER_TBANK,
                status="pending",
                credits_amount=credits,
                currency="RUB",
                amount_original=amount_rub,
                discount_amount=discount_amount,
                amount_final=amount_final,
                metadata_json=metadata_json,
            )
            session.add(checkout)
            session.flush()

            payment = Payment(
                account_id=account_uuid,
                checkout_session_id=checkout.id,
                promocode_id=(promo_result["promocode_id"] if promo_result is not None else None),
                price_original=amount_rub,
                discount_amount=discount_amount,
                price_final=amount_final,
                currency="RUB",
                status="pending",
                provider=BILLING_PROVIDER_TBANK,
                credits_amount=credits,
            )
            session.add(payment)
            session.flush()

            if promo_result is not None:
                promo_result["usage"].payment_id = payment.id

            session.commit()
            return {
                "status": "ok",
                "checkout_id": str(checkout.id),
                "payment_id": str(payment.id),
                "amount_final": str(amount_final.quantize(Decimal("0.01"))),
            }

    def _mark_checkout_initialized(
        self,
        *,
        checkout_id: str,
        payment_id: str,
        provider_payment_id: str,
        checkout_url: str,
        provider_status: str | None,
        provider_raw: dict | None,
    ) -> None:
        with get_db_session() as session:
            checkout = (
                session.query(CheckoutSession)
                .filter(CheckoutSession.id == UUID(checkout_id))
                .with_for_update()
                .first()
            )
            payment = (
                session.query(Payment)
                .filter(Payment.id == UUID(payment_id))
                .with_for_update()
                .first()
            )
            if checkout is None or payment is None:
                return
            checkout.status = "invoice_sent"
            checkout.provider_checkout_id = provider_payment_id
            existing_metadata = checkout.metadata_json if isinstance(checkout.metadata_json, dict) else {}
            checkout.metadata_json = {
                **existing_metadata,
                "checkout_url": checkout_url,
                "provider_status": provider_status,
                "provider_raw": provider_raw,
            }
            payment.provider_payment_id = provider_payment_id
            payment.status = "invoice_sent"
            session.add(
                BillingEvent(
                    provider=BILLING_PROVIDER_TBANK,
                    event_type="tbank_payment_initialized",
                    account_id=checkout.account_id,
                    payment_id=payment.id,
                    provider_payment_id=provider_payment_id,
                    currency="RUB",
                    provider_amount=payment.price_final,
                    credits_amount=int(payment.credits_amount or 0),
                    meta_json='{"source":"web_checkout"}',
                )
            )
            session.commit()

    def _mark_checkout_init_failed(self, checkout_id: str, payment_id: str, reason: str) -> None:
        with get_db_session() as session:
            checkout = (
                session.query(CheckoutSession)
                .filter(CheckoutSession.id == UUID(checkout_id))
                .with_for_update()
                .first()
            )
            payment = (
                session.query(Payment)
                .filter(Payment.id == UUID(payment_id))
                .with_for_update()
                .first()
            )
            if checkout is None or payment is None:
                return
            now = utcnow()
            checkout.status = "init_failed"
            payment.status = "init_failed"
            payment.refund_reason = str(reason or "init_failed")[:256] or None
            self._release_promocode_for_payment_sync(
                session=session,
                payment=payment,
                now=now,
                reason="checkout_init_failed",
            )
            session.add(
                BillingEvent(
                    provider=BILLING_PROVIDER_TBANK,
                    event_type="tbank_payment_init_failed",
                    account_id=checkout.account_id,
                    payment_id=payment.id,
                    currency="RUB",
                    provider_amount=payment.price_final,
                    credits_amount=int(payment.credits_amount or 0),
                    reason=str(reason or "init_failed")[:128] or None,
                )
            )
            session.commit()

    def _get_checkout_snapshot(self, account_id: str, checkout_id: str) -> dict | None:
        try:
            account_uuid = UUID(account_id)
            checkout_uuid = UUID(checkout_id)
        except Exception:
            return None
        with get_db_session() as session:
            checkout = (
                session.query(CheckoutSession)
                .filter(
                    CheckoutSession.id == checkout_uuid,
                    CheckoutSession.account_id == account_uuid,
                )
                .first()
            )
            if checkout is None:
                return None
            payment = (
                session.query(Payment)
                .filter(Payment.checkout_session_id == checkout.id)
                .order_by(Payment.created_at.desc())
                .first()
            )
            return _serialize_checkout(checkout, payment)

    def _apply_tbank_notification_sync(
        self,
        *,
        order_id: str,
        provider_payment_id: str | None,
        status: str | None,
        success: bool,
        amount_kopecks: int | None,
        payload: dict[str, object] | None,
        accept_statuses: set[str] | None,
    ) -> dict:
        accepted = {item.upper() for item in (accept_statuses or {"CONFIRMED", "AUTHORIZED"})}
        normalized_status = str(status or "").strip().upper()
        provider_id = str(provider_payment_id or "").strip() or None
        try:
            order_uuid = UUID(str(order_id or "").strip())
        except Exception:
            return {"status": "invalid_order_id"}

        with get_db_session() as session:
            payment = (
                session.query(Payment)
                .filter(
                    Payment.id == order_uuid,
                    Payment.provider == BILLING_PROVIDER_TBANK,
                )
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if payment.account_id is None:
                return {"status": "not_applicable"}

            checkout = (
                session.query(CheckoutSession)
                .filter(CheckoutSession.id == payment.checkout_session_id)
                .with_for_update()
                .first()
            )
            if provider_id and not payment.provider_payment_id:
                payment.provider_payment_id = provider_id
            if checkout is not None and provider_id and not checkout.provider_checkout_id:
                checkout.provider_checkout_id = provider_id

            expected_kopecks = int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1")))
            if amount_kopecks is not None and int(amount_kopecks) != expected_kopecks:
                emit_observability_event(
                    logger,
                    "billing_notification_invalid_amount",
                    level="warning",
                    account_id=str(payment.account_id),
                    payment_id=str(payment.id),
                    checkout_id=str(checkout.id) if checkout is not None else None,
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    expected_kopecks=expected_kopecks,
                    amount_kopecks=amount_kopecks,
                    status=normalized_status or None,
                )
                session.commit()
                return {"status": "invalid_amount"}

            if normalized_status in REFUND_LIKE_TBANK_STATUSES:
                return self._apply_web_refund_notification(
                    session=session,
                    payment=payment,
                    checkout=checkout,
                    provider_id=provider_id,
                    normalized_status=normalized_status,
                    amount_kopecks=amount_kopecks if amount_kopecks is not None else expected_kopecks,
                )

            if not success or normalized_status not in accepted:
                if payment.status in {"pending", "invoice_sent"}:
                    now = utcnow()
                    mapped_status = normalized_status.lower() if normalized_status else "failed"
                    payment.status = mapped_status[:32]
                    if checkout is not None:
                        checkout.status = payment.status
                    self._release_promocode_for_payment_sync(
                        session=session,
                        payment=payment,
                        now=now,
                        reason=f"checkout_{payment.status}",
                    )

                emit_observability_event(
                    logger,
                    "billing_notification_ignored",
                    level="warning",
                    account_id=str(payment.account_id),
                    payment_id=str(payment.id),
                    checkout_id=str(checkout.id) if checkout is not None else None,
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    provider_status=normalized_status or None,
                    success=success,
                    payment_status=payment.status,
                )
                session.add(
                    BillingEvent(
                        provider=BILLING_PROVIDER_TBANK,
                        event_type="tbank_payment_status_ignored",
                        account_id=payment.account_id,
                        payment_id=payment.id,
                        provider_payment_id=provider_id or payment.provider_payment_id,
                        currency=payment.currency,
                        provider_amount=payment.price_final,
                        credits_amount=int(payment.credits_amount or 0),
                        reason=f"status_{normalized_status or 'unknown'}"[:128],
                    )
                )
                session.commit()
                return {"status": "ignored", "payment_status": payment.status}

            if payment.status == "paid":
                snapshot = get_account_balance_snapshot(session, payment.account_id)
                session.commit()
                return {
                    "status": "duplicate",
                    "payment_id": str(payment.id),
                    "account_id": str(payment.account_id),
                    "credits": int(payment.credits_amount or 0),
                    "remaining_requests": snapshot["credits"],
                }

            payment.status = "paid"
            payment.paid_at = utcnow()
            if checkout is not None:
                checkout.status = "paid"
                checkout.completed_at = payment.paid_at
            self._redeem_promocode_for_payment_sync(
                session=session,
                payment=payment,
                now=payment.paid_at,
            )

            session.add(
                BillingEvent(
                    provider=BILLING_PROVIDER_TBANK,
                    event_type="tbank_payment_paid",
                    account_id=payment.account_id,
                    payment_id=payment.id,
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    currency=payment.currency,
                    provider_amount=payment.price_final,
                    credits_amount=int(payment.credits_amount or 0),
                )
            )
            append_flow_event(
                session,
                account_id=payment.account_id,
                event_type=EVENT_CHECKOUT_PAID,
                screen_key="billing",
                action_key="checkout_paid",
                source="worker_webhook",
                meta={
                    "payment_id": str(payment.id),
                    "checkout_id": str(checkout.id) if checkout is not None else None,
                    "credits": int(payment.credits_amount or 0),
                },
            )
            snapshot = get_account_balance_snapshot(session, payment.account_id)
            session.commit()
            return {
                "status": "applied",
                "payment_id": str(payment.id),
                "account_id": str(payment.account_id),
                "credits": int(payment.credits_amount or 0),
                "remaining_requests": snapshot["credits"],
            }

    def _apply_web_refund_notification(
        self,
        *,
        session,
        payment: Payment,
        checkout: CheckoutSession | None,
        provider_id: str | None,
        normalized_status: str,
        amount_kopecks: int,
    ) -> dict:
        if payment.status == "refunded":
            snapshot = get_account_balance_snapshot(session, payment.account_id)
            session.commit()
            return {
                "status": "duplicate_refund",
                "payment_id": str(payment.id),
                "account_id": str(payment.account_id),
                "remaining_requests": snapshot["credits"],
            }

        if payment.status in {"pending", "invoice_sent", "authorized", "confirmed", "init_failed"}:
            now = utcnow()
            payment.status = "canceled"
            if checkout is not None:
                checkout.status = "canceled"
                checkout.completed_at = now
            self._release_promocode_for_payment_sync(
                session=session,
                payment=payment,
                now=now,
                reason=f"checkout_{normalized_status.lower()}",
            )
            emit_observability_event(
                logger,
                "billing_checkout_canceled",
                level="warning",
                account_id=str(payment.account_id),
                payment_id=str(payment.id),
                checkout_id=str(checkout.id) if checkout is not None else None,
                provider_payment_id=provider_id or payment.provider_payment_id,
                provider_status=normalized_status,
            )
            session.add(
                BillingEvent(
                    provider=BILLING_PROVIDER_TBANK,
                    event_type="tbank_payment_canceled",
                    account_id=payment.account_id,
                    payment_id=payment.id,
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    currency=payment.currency,
                    provider_amount=payment.price_final,
                    credits_amount=int(payment.credits_amount or 0),
                    reason=f"status_{normalized_status}"[:128],
                )
            )
            session.commit()
            return {"status": "canceled", "payment_status": payment.status}

        if payment.status != "paid":
            session.commit()
            return {"status": "refund_ignored", "payment_status": payment.status}

        payment.status = "refunded"
        payment.refunded_at = utcnow()
        payment.refund_reason = f"tbank_webhook_{normalized_status.lower()[:32]}"
        if checkout is not None:
            checkout.status = "refunded"
            checkout.completed_at = payment.refunded_at
        emit_observability_event(
            logger,
            "billing_checkout_refunded",
            level="warning",
            account_id=str(payment.account_id),
            payment_id=str(payment.id),
            checkout_id=str(checkout.id) if checkout is not None else None,
            provider_payment_id=provider_id or payment.provider_payment_id,
            provider_status=normalized_status,
        )
        session.add(
            BillingEvent(
                provider=BILLING_PROVIDER_TBANK,
                event_type="tbank_payment_refunded",
                account_id=payment.account_id,
                payment_id=payment.id,
                provider_payment_id=provider_id or payment.provider_payment_id,
                currency=payment.currency,
                provider_amount=(Decimal(amount_kopecks) / Decimal("100")),
                credits_amount=int(payment.credits_amount or 0),
                reason=f"status_{normalized_status}"[:128],
            )
        )
        append_flow_event(
            session,
            account_id=payment.account_id,
            event_type=EVENT_CHECKOUT_REFUNDED,
            screen_key="billing",
            action_key="checkout_refunded",
            source="worker_webhook",
            meta={
                "payment_id": str(payment.id),
                "checkout_id": str(checkout.id) if checkout is not None else None,
                "credits": int(payment.credits_amount or 0),
            },
        )
        snapshot = get_account_balance_snapshot(session, payment.account_id)
        session.commit()
        return {
            "status": "refunded",
            "payment_id": str(payment.id),
            "account_id": str(payment.account_id),
            "credits": int(payment.credits_amount or 0),
            "remaining_requests": snapshot["credits"],
        }

    def _get_catalog_amount(self, provider: str, credits: int) -> Decimal | None:
        if provider != BILLING_PROVIDER_TBANK:
            return None
        catalog = parse_tbank_package_catalog(self._settings.WEB_TBANK_PACKAGE_CATALOG_RUB_JSON)
        return catalog.get(int(credits or 0))

    def _evaluate_promocode(
        self,
        *,
        session,
        account_id: UUID,
        code: str,
        credits: int,
        amount_rub: Decimal,
    ) -> dict:
        normalized = self._normalize_promocode_code(code)
        if not normalized:
            return {"status": "invalid", "reason": "empty_code"}

        now = utcnow()
        promo = (
            session.query(Promocode)
            .filter(func.lower(Promocode.code_string) == normalized.lower())
            .with_for_update()
            .first()
        )
        if promo is None:
            return {"status": "invalid", "reason": "not_found"}

        active, reason = self._is_promocode_active(promo, now)
        if not active:
            return {"status": "invalid", "reason": reason}

        if promo.code_amount is not None and self._promo_code_left(promo) <= 0:
            return {"status": "invalid", "reason": "code_exhausted"}

        if bool(promo.is_new_users_only) and not self._is_account_new_for_promocode(
            session=session,
            account_id=account_id,
        ):
            return {"status": "invalid", "reason": "new_users_only"}

        max_uses = int(promo.max_uses_per_user or 0)
        if max_uses > 0:
            used_count = (
                session.query(func.count(PromocodeUsage.id))
                .filter(
                    PromocodeUsage.code_id == promo.id,
                    PromocodeUsage.account_id == account_id,
                    PromocodeUsage.status == PROMO_USAGE_STATUS_REDEEMED,
                )
                .scalar()
            )
            if int(used_count or 0) >= max_uses:
                return {"status": "invalid", "reason": "max_uses_per_user_reached"}

        pricing = self._compute_promocode_pricing(promo, amount_rub)
        if pricing is None:
            return {"status": "invalid", "reason": "invalid_discount"}

        return {
            "status": "ok",
            "promo": promo,
            "code": promo.code_string,
            "discount_type": str(promo.discount_type or "").strip().lower(),
            "discount_value": str(Decimal(str(promo.discount_amount or "0")).quantize(Decimal("0.01"))),
            "credits_amount": int(credits or 0),
            "currency": "RUB",
            "amount_original_decimal": pricing["amount_original"],
            "discount_amount_decimal": pricing["discount_amount"],
            "amount_final_decimal": pricing["amount_final"],
            "code_left": self._promo_code_left(promo) if promo.code_amount is not None else None,
        }

    def _serialize_promocode_preview(self, result: dict) -> dict:
        return {
            "status": "ok",
            "code": result["code"],
            "discount_type": result["discount_type"],
            "discount_value": result["discount_value"],
            "credits_amount": result["credits_amount"],
            "currency": result["currency"],
            "amount_original": str(result["amount_original_decimal"].quantize(Decimal("0.01"))),
            "discount_amount": str(result["discount_amount_decimal"].quantize(Decimal("0.01"))),
            "amount_final": str(result["amount_final_decimal"].quantize(Decimal("0.01"))),
            "code_left": result["code_left"],
        }

    def _reserve_promocode_for_checkout(
        self,
        *,
        session,
        account_id: UUID,
        code: str,
        credits: int,
        amount_rub: Decimal,
    ) -> dict:
        result = self._evaluate_promocode(
            session=session,
            account_id=account_id,
            code=code,
            credits=credits,
            amount_rub=amount_rub,
        )
        if result.get("status") != "ok":
            return result

        promo = result["promo"]
        now = utcnow()
        if promo.code_amount is not None:
            current_left = self._promo_code_left(promo)
            if current_left <= 0:
                return {"status": "invalid", "reason": "code_exhausted"}
            promo.code_left = current_left - 1

        usage = PromocodeUsage(
            code_id=promo.id,
            user_id=None,
            account_id=account_id,
            payment_id=None,
            status=PROMO_USAGE_STATUS_RESERVED,
            reserved_at=now,
            expires_at=None,
            released_at=None,
            redeemed_at=None,
            release_reason=None,
            credits_amount=result["credits_amount"],
            price_original=result["amount_original_decimal"],
            discount_amount=result["discount_amount_decimal"],
            price_final=result["amount_final_decimal"],
            used_at=now,
        )
        session.add(usage)
        session.flush()

        return {
            "status": "ok",
            "usage": usage,
            "promocode_id": promo.id,
            "code": result["code"],
            "discount_type": result["discount_type"],
            "discount_value": result["discount_value"],
            "discount_amount_decimal": result["discount_amount_decimal"],
            "amount_final_decimal": result["amount_final_decimal"],
        }

    def _release_promocode_for_payment_sync(self, *, session, payment: Payment, now, reason: str) -> None:
        usage = (
            session.query(PromocodeUsage)
            .filter(
                PromocodeUsage.payment_id == payment.id,
                PromocodeUsage.status == PROMO_USAGE_STATUS_RESERVED,
            )
            .with_for_update()
            .first()
        )
        if usage is None:
            return
        self._mark_promocode_usage_released(usage=usage, now=now, reason=reason)
        session.flush()

    def _redeem_promocode_for_payment_sync(self, *, session, payment: Payment, now) -> None:
        usage = (
            session.query(PromocodeUsage)
            .filter(
                PromocodeUsage.payment_id == payment.id,
                PromocodeUsage.status == PROMO_USAGE_STATUS_RESERVED,
            )
            .with_for_update()
            .first()
        )
        if usage is None:
            return
        usage.status = PROMO_USAGE_STATUS_REDEEMED
        usage.redeemed_at = now
        usage.used_at = now
        usage.released_at = None
        usage.release_reason = None
        session.flush()

    @staticmethod
    def _normalize_promocode_code(code: str) -> str:
        return "".join(str(code or "").strip().split()).upper()[:64]

    @staticmethod
    def _promo_code_left(promo: Promocode) -> int:
        if promo.code_amount is None:
            return 0
        if promo.code_left is None:
            return int(max(int(promo.code_amount), 0))
        return int(max(int(promo.code_left), 0))

    @staticmethod
    def _is_promocode_active(promo: Promocode, now) -> tuple[bool, str | None]:
        if not bool(promo.is_active):
            return False, "code_inactive"
        if promo.starts_at and promo.starts_at > now:
            return False, "code_not_started"
        if promo.ends_at and promo.ends_at < now:
            return False, "code_expired"
        return True, None

    @staticmethod
    def _mark_promocode_usage_released(*, usage: PromocodeUsage, now, reason: str) -> None:
        if usage.status != PROMO_USAGE_STATUS_RESERVED:
            return
        promo = usage.promocode
        if promo is not None and promo.code_amount is not None:
            current_left = CheckoutService._promo_code_left(promo)
            promo.code_left = min(int(promo.code_amount), current_left + 1)
        usage.status = PROMO_USAGE_STATUS_EXPIRED if reason == "ttl_expired" else PROMO_USAGE_STATUS_RELEASED
        usage.released_at = now
        usage.release_reason = str(reason or "released")[:64]

    @staticmethod
    def _is_account_new_for_promocode(*, session, account_id: UUID) -> bool:
        paid_count = (
            session.query(func.count(Payment.id))
            .filter(
                Payment.account_id == account_id,
                Payment.provider == BILLING_PROVIDER_TBANK,
                Payment.paid_at.is_not(None),
            )
            .scalar()
        )
        return int(paid_count or 0) == 0

    @staticmethod
    def _compute_promocode_pricing(promo: Promocode, amount_original: Decimal) -> dict[str, Decimal] | None:
        original = Decimal(str(amount_original or "0")).quantize(Decimal("0.01"))
        if original <= 0:
            return None
        discount_type = str(promo.discount_type or "").strip().lower()
        amount_raw = Decimal(str(promo.discount_amount or "0"))
        if amount_raw <= 0:
            return None
        if discount_type == "percent":
            discount = (original * amount_raw / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        elif discount_type == "fixed":
            discount = amount_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            return None
        if discount <= 0:
            return None
        final = (original - discount).quantize(Decimal("0.01"))
        if final <= 0:
            return None
        return {
            "amount_original": original,
            "discount_amount": discount,
            "amount_final": final,
        }


def _serialize_checkout(checkout: CheckoutSession, payment: Payment | None) -> dict:
    metadata = checkout.metadata_json or {}
    promo_meta = metadata.get("promocode") if isinstance(metadata, dict) else None
    return {
        "id": str(checkout.id),
        "provider": checkout.provider,
        "status": checkout.status,
        "credits_amount": int(checkout.credits_amount or 0),
        "currency": checkout.currency,
        "amount_original": (
            str(Decimal(checkout.amount_original).quantize(Decimal("0.01")))
            if checkout.amount_original is not None
            else None
        ),
        "discount_amount": (
            str(Decimal(checkout.discount_amount).quantize(Decimal("0.01")))
            if checkout.discount_amount is not None
            else None
        ),
        "amount_final": (
            str(Decimal(checkout.amount_final).quantize(Decimal("0.01")))
            if checkout.amount_final is not None
            else None
        ),
        "provider_checkout_id": checkout.provider_checkout_id,
        "checkout_url": metadata.get("checkout_url") if isinstance(metadata, dict) else None,
        "promocode_code": (
            promo_meta.get("code")
            if isinstance(promo_meta, dict)
            else (payment.promocode.code_string if payment is not None and payment.promocode is not None else None)
        ),
        "created_at": checkout.created_at,
        "updated_at": checkout.updated_at,
        "completed_at": checkout.completed_at,
        "expires_at": checkout.expires_at,
        "payment": _serialize_payment(payment) if payment is not None else None,
    }


def _serialize_payment(payment: Payment) -> dict:
    return {
        "id": str(payment.id),
        "provider": payment.provider,
        "status": payment.status,
        "credits_amount": int(payment.credits_amount or 0),
        "currency": payment.currency,
        "price_original": str(Decimal(payment.price_original or 0).quantize(Decimal("0.01"))),
        "discount_amount": str(Decimal(payment.discount_amount or 0).quantize(Decimal("0.01"))),
        "price_final": str(Decimal(payment.price_final or 0).quantize(Decimal("0.01"))),
        "provider_payment_id": payment.provider_payment_id,
        "checkout_session_id": str(payment.checkout_session_id) if payment.checkout_session_id else None,
        "promocode_code": payment.promocode.code_string if payment.promocode is not None else None,
        "created_at": payment.created_at,
        "paid_at": payment.paid_at,
        "refunded_at": payment.refunded_at,
    }
