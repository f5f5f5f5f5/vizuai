from __future__ import annotations

import asyncio
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
from uuid import UUID

from sqlalchemy import func

from models.billing_event_model import BillingEvent
from models.billing_webhook_event_model import BillingWebhookEvent
from models.payment_model import Payment
from models.promocode_model import Promocode
from models.promocode_usage_model import PromocodeUsage
from models.user_flow_event_model import UserFlowEvent
from models.user_model import User
from services.db_connection import get_db_session
from utils.time import utcnow

logger = logging.getLogger("whitelist")

CREDITS_STATUS_ACTIVE = "active"
CREDITS_STATUS_EXHAUSTED = "exhausted"
CREDITS_STATUS_NO_CREDITS = "no_credits"
PAYMENT_STATUS_REFUND_PENDING = "refund_pending"
PAYMENT_STATUS_REFUNDED = "refunded"
PROMO_USAGE_STATUS_RESERVED = "reserved"
PROMO_USAGE_STATUS_REDEEMED = "redeemed"
PROMO_USAGE_STATUS_RELEASED = "released"
PROMO_USAGE_STATUS_EXPIRED = "expired"
DEFAULT_PROMO_RESERVATION_TTL_SECONDS = 60 * 60
PROVIDER_STARS = "telegram_stars"
PROVIDER_TBANK = "tbank_sbp"
BILLING_REPORT_PROVIDERS = (PROVIDER_STARS, PROVIDER_TBANK)


class WhitelistService:
    def __init__(self) -> None:
        self._session_factory = get_db_session
        self._supported_billing_providers = set(BILLING_REPORT_PROVIDERS)

    def _normalize_billing_provider(self, provider: str | None) -> str | None:
        value = str(provider or "").strip().lower()
        if value in self._supported_billing_providers:
            return value
        return None

    def _unsupported_provider(self, provider: str | None) -> dict:
        return {
            "status": "unsupported_provider",
            "provider": str(provider or "").strip().lower() or None,
            "supported": sorted(self._supported_billing_providers),
        }

    async def ensure_user(
        self,
        user_id: int,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        acquisition_source: str | None = None,
    ) -> User:
        return await asyncio.to_thread(
            self._ensure_user_sync, user_id, username, first_name, last_name, acquisition_source
        )

    async def record_screen_view(
        self,
        user_id: int,
        screen_key: str,
        *,
        source: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_user_flow_event_sync,
            user_id,
            "screen_view",
            screen_key,
            None,
            source,
            meta,
            True,
        )

    async def record_action_click(
        self,
        user_id: int,
        action_key: str,
        *,
        source: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_user_flow_event_sync,
            user_id,
            "action_click",
            None,
            action_key,
            source,
            meta,
            False,
        )

    async def get_flow_report(
        self, days: int = 7, acquisition_source: str | None = None
    ) -> dict:
        return await asyncio.to_thread(self._get_flow_report_sync, days, acquisition_source)

    async def get_flow_user_report(self, user_id: int, days: int = 30) -> dict:
        return await asyncio.to_thread(self._get_flow_user_report_sync, user_id, days)

    async def is_user_whitelisted(self, user_id: int) -> bool:
        status = await self.get_whitelist_status(user_id)
        return status["whitelisted"]

    async def add_user_to_whitelist(
        self,
        user_id: int,
        days: int | None = None,
        requests: int | None = None,
    ) -> User | None:
        return await asyncio.to_thread(self._add_user_sync, user_id, days, requests)

    async def remove_user_from_whitelist(self, user_id: int) -> User | None:
        return await asyncio.to_thread(self._remove_user_sync, user_id)

    async def get_whitelist_status(self, user_id: int) -> dict:
        return await asyncio.to_thread(self._get_status_sync, user_id)

    async def record_request(self, user_id: int, count: int = 1) -> User | None:
        return await asyncio.to_thread(self._record_request_sync, user_id, count)

    async def list_whitelisted_users(self) -> list[dict]:
        return await asyncio.to_thread(self._list_whitelisted_sync)

    async def reset_quota(self, user_id: int) -> User | None:
        return await asyncio.to_thread(self._reset_quota_sync, user_id)

    async def reserve_units(self, user_id: int, units: int) -> dict:
        return await asyncio.to_thread(self._reserve_units_sync, user_id, units)

    async def apply_stars_payment(
        self,
        user_id: int,
        credits: int,
        stars_amount: int,
        provider_payment_id: str,
        telegram_payment_charge_id: str | None = None,
        promo_reservation_id: str | None = None,
        promo_code_id: str | None = None,
        stars_original: int | None = None,
        discount_stars: int | None = None,
        checkout_payment_id: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._apply_stars_payment_sync,
            user_id,
            credits,
            stars_amount,
            provider_payment_id,
            telegram_payment_charge_id,
            promo_reservation_id,
            promo_code_id,
            stars_original,
            discount_stars,
            checkout_payment_id,
        )

    async def create_tbank_payment_intent(
        self,
        *,
        user_id: int,
        credits: int,
        amount_rub: Decimal,
        promo_reservation_id: str | None = None,
        promo_code_id: str | None = None,
        amount_original_rub: Decimal | None = None,
        discount_rub: Decimal | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._create_tbank_payment_intent_sync,
            user_id,
            credits,
            amount_rub,
            promo_reservation_id,
            promo_code_id,
            amount_original_rub,
            discount_rub,
        )

    async def create_stars_payment_intent(
        self,
        *,
        user_id: int,
        credits: int,
        stars_amount: int,
        promo_reservation_id: str | None = None,
        promo_code_id: str | None = None,
        stars_original: int | None = None,
        discount_stars: int | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._create_stars_payment_intent_sync,
            user_id,
            credits,
            stars_amount,
            promo_reservation_id,
            promo_code_id,
            stars_original,
            discount_stars,
        )

    async def create_checkout_intent(
        self,
        *,
        provider: str,
        user_id: int,
        credits: int,
        amount: Decimal | int,
        currency: str,
        promo_reservation_id: str | None = None,
        promo_code_id: str | None = None,
        amount_original: Decimal | int | None = None,
        discount_amount: Decimal | int | None = None,
    ) -> dict:
        provider_name = self._normalize_billing_provider(provider)
        if provider_name is None:
            return self._unsupported_provider(provider)
        normalized_currency = str(currency or "").strip().upper()
        if provider_name == PROVIDER_STARS:
            if normalized_currency != "XTR":
                return {"status": "invalid_currency", "currency": normalized_currency}
            return await self.create_stars_payment_intent(
                user_id=user_id,
                credits=credits,
                stars_amount=int(amount),
                promo_reservation_id=promo_reservation_id,
                promo_code_id=promo_code_id,
                stars_original=(int(amount_original) if amount_original is not None else None),
                discount_stars=(int(discount_amount) if discount_amount is not None else None),
            )
        if provider_name == PROVIDER_TBANK:
            if normalized_currency != "RUB":
                return {"status": "invalid_currency", "currency": normalized_currency}
            amount_rub = amount if isinstance(amount, Decimal) else Decimal(str(amount))
            original_rub = (
                amount_original
                if isinstance(amount_original, Decimal)
                else (Decimal(str(amount_original)) if amount_original is not None else None)
            )
            discount_rub = (
                discount_amount
                if isinstance(discount_amount, Decimal)
                else (Decimal(str(discount_amount)) if discount_amount is not None else None)
            )
            return await self.create_tbank_payment_intent(
                user_id=user_id,
                credits=credits,
                amount_rub=amount_rub,
                promo_reservation_id=promo_reservation_id,
                promo_code_id=promo_code_id,
                amount_original_rub=original_rub,
                discount_rub=discount_rub,
            )
        return self._unsupported_provider(provider)

    async def mark_stars_payment_invoice_sent(
        self,
        *,
        payment_id: str,
        invoice_meta: dict[str, object] | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._mark_stars_payment_invoice_sent_sync,
            payment_id,
            invoice_meta,
        )

    async def mark_stars_payment_failed(
        self,
        *,
        payment_id: str,
        reason: str,
        error_meta: dict[str, object] | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._mark_stars_payment_failed_sync,
            payment_id,
            reason,
            error_meta,
        )

    async def validate_stars_checkout_intent(
        self,
        *,
        payment_id: str,
        user_id: int,
        credits: int,
        stars_amount: int,
    ) -> dict:
        return await asyncio.to_thread(
            self._validate_stars_checkout_intent_sync,
            payment_id,
            user_id,
            credits,
            stars_amount,
        )

    async def mark_tbank_payment_initialized(
        self,
        *,
        payment_id: str,
        provider_payment_id: str,
        init_meta: dict[str, object] | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._mark_tbank_payment_initialized_sync,
            payment_id,
            provider_payment_id,
            init_meta,
        )

    async def mark_tbank_payment_failed(
        self,
        *,
        payment_id: str,
        reason: str,
        error_meta: dict[str, object] | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._mark_tbank_payment_failed_sync,
            payment_id,
            reason,
            error_meta,
        )

    async def apply_tbank_notification(
        self,
        *,
        order_id: str,
        provider_payment_id: str | None,
        status: str | None,
        success: bool,
        amount_kopecks: int | None,
        payload: dict[str, object] | None = None,
        accept_statuses: set[str] | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._apply_tbank_notification_sync,
            order_id,
            provider_payment_id,
            status,
            success,
            amount_kopecks,
            payload,
            accept_statuses,
        )

    async def check_promocode(self, user_id: int, code: str) -> dict:
        return await asyncio.to_thread(self._check_promocode_sync, user_id, code)

    async def reserve_promocode(
        self,
        *,
        user_id: int,
        code: str,
        credits: int,
        stars_original: int,
        ttl_seconds: int = DEFAULT_PROMO_RESERVATION_TTL_SECONDS,
        previous_reservation_id: str | None = None,
        provider: str = PROVIDER_STARS,
        currency: str = "XTR",
    ) -> dict:
        return await asyncio.to_thread(
            self._reserve_promocode_sync,
            user_id,
            code,
            credits,
            stars_original,
            ttl_seconds,
            previous_reservation_id,
            provider,
            currency,
        )

    async def release_promocode_reservation(
        self,
        reservation_id: str,
        *,
        user_id: int,
        reason: str,
        provider: str = PROVIDER_STARS,
        currency: str = "XTR",
    ) -> dict:
        return await asyncio.to_thread(
            self._release_promocode_reservation_sync,
            reservation_id,
            user_id,
            reason,
            provider,
            currency,
        )

    async def validate_promocode_reservation(
        self,
        *,
        reservation_id: str,
        user_id: int,
        promo_code_id: str,
        credits: int,
        stars_original: int,
        discount_stars: int,
        stars_final: int,
    ) -> dict:
        return await asyncio.to_thread(
            self._validate_promocode_reservation_sync,
            reservation_id,
            user_id,
            promo_code_id,
            credits,
            stars_original,
            discount_stars,
            stars_final,
        )

    async def record_billing_event(
        self,
        *,
        provider: str,
        event_type: str,
        user_id: int | None = None,
        payment_id: str | None = None,
        provider_payment_id: str | None = None,
        telegram_payment_charge_id: str | None = None,
        currency: str | None = None,
        stars_amount: int | None = None,
        provider_amount: Decimal | int | float | str | None = None,
        credits_amount: int | None = None,
        reason: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._record_billing_event_sync,
            provider,
            event_type,
            user_id,
            payment_id,
            provider_payment_id,
            telegram_payment_charge_id,
            currency,
            stars_amount,
            provider_amount,
            credits_amount,
            reason,
            meta,
        )

    async def get_billing_report(self, days: int = 7) -> dict:
        return await asyncio.to_thread(self._get_billing_report_sync, days)

    async def get_billing_suspicious(
        self,
        days: int = 7,
        refund_pending_minutes: int = 10,
    ) -> dict:
        return await asyncio.to_thread(
            self._get_billing_suspicious_sync,
            days,
            refund_pending_minutes,
        )

    async def get_billing_user_report(self, user_id: int, days: int = 30) -> dict:
        return await asyncio.to_thread(self._get_billing_user_report_sync, user_id, days)

    async def get_billing_reconciliation(
        self,
        *,
        limit_users: int = 20,
        min_abs_delta: int = 1,
    ) -> dict:
        return await asyncio.to_thread(
            self._get_billing_reconciliation_sync,
            limit_users,
            min_abs_delta,
        )

    async def register_webhook_event(
        self,
        *,
        provider: str,
        event_type: str,
        idempotency_key: str,
        order_id: str | None = None,
        provider_payment_id: str | None = None,
        payload: dict[str, object] | None = None,
        max_attempts: int = 3,
    ) -> dict:
        return await asyncio.to_thread(
            self._register_webhook_event_sync,
            provider,
            event_type,
            idempotency_key,
            order_id,
            provider_payment_id,
            payload,
            max_attempts,
        )

    async def finalize_webhook_event(
        self,
        *,
        event_id: str,
        status: str,
        error: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._finalize_webhook_event_sync,
            event_id,
            status,
            error,
        )

    async def get_webhook_event(self, event_id: str) -> dict:
        return await asyncio.to_thread(self._get_webhook_event_sync, event_id)

    async def list_webhook_dead_letters(self, *, provider: str, limit: int = 20) -> dict:
        return await asyncio.to_thread(
            self._list_webhook_dead_letters_sync,
            provider,
            limit,
        )

    async def lookup_stars_payment(self, query: str) -> dict:
        return await asyncio.to_thread(self._lookup_stars_payment_sync, query)

    async def lookup_tbank_payment(self, query: str) -> dict:
        return await asyncio.to_thread(self._lookup_tbank_payment_sync, query)

    async def lookup_payment(self, provider: str, query: str) -> dict:
        provider_name = self._normalize_billing_provider(provider)
        if provider_name is None:
            return self._unsupported_provider(provider)
        if provider_name == PROVIDER_STARS:
            return await self.lookup_stars_payment(query)
        if provider_name == PROVIDER_TBANK:
            return await self.lookup_tbank_payment(query)
        return self._unsupported_provider(provider)

    async def get_tbank_payment_link_message(self, payment_id: str) -> dict:
        return await asyncio.to_thread(self._get_tbank_payment_link_message_sync, payment_id)

    async def start_stars_refund(self, payment_id: str) -> dict:
        return await asyncio.to_thread(self._start_stars_refund_sync, payment_id)

    async def start_tbank_refund(self, payment_id: str) -> dict:
        return await asyncio.to_thread(self._start_tbank_refund_sync, payment_id)

    async def start_refund(self, provider: str, payment_id: str) -> dict:
        provider_name = self._normalize_billing_provider(provider)
        if provider_name is None:
            return self._unsupported_provider(provider)
        if provider_name == PROVIDER_STARS:
            return await self.start_stars_refund(payment_id)
        if provider_name == PROVIDER_TBANK:
            return await self.start_tbank_refund(payment_id)
        return self._unsupported_provider(provider)

    async def finalize_stars_refund(
        self,
        payment_id: str,
        *,
        success: bool,
        reason: str | None = None,
        telegram_error: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._finalize_stars_refund_sync,
            payment_id,
            success,
            reason,
            telegram_error,
        )

    async def finalize_tbank_refund(
        self,
        payment_id: str,
        *,
        success: bool,
        reason: str | None = None,
        tbank_error: str | None = None,
        tbank_status: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._finalize_tbank_refund_sync,
            payment_id,
            success,
            reason,
            tbank_error,
            tbank_status,
        )

    async def finalize_refund(
        self,
        provider: str,
        payment_id: str,
        *,
        success: bool,
        reason: str | None = None,
        error: str | None = None,
        status: str | None = None,
    ) -> dict:
        provider_name = self._normalize_billing_provider(provider)
        if provider_name is None:
            return self._unsupported_provider(provider)
        if provider_name == PROVIDER_STARS:
            return await self.finalize_stars_refund(
                payment_id,
                success=success,
                reason=reason,
                telegram_error=error,
            )
        if provider_name == PROVIDER_TBANK:
            return await self.finalize_tbank_refund(
                payment_id,
                success=success,
                reason=reason,
                tbank_error=error,
                tbank_status=status,
            )
        return self._unsupported_provider(provider)

    def _ensure_user_sync(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        last_name: str | None,
        acquisition_source: str | None,
    ) -> User:
        recorded_at = utcnow() if acquisition_source else None
        with self._session_factory() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                user = User(
                    user_id=user_id,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    is_active=False,
                    credits_status=CREDITS_STATUS_NO_CREDITS,
                    usage_left=0,
                    acquisition_source=acquisition_source,
                    acquisition_recorded_at=recorded_at,
                )
                session.add(user)
                session.commit()
                session.refresh(user)
                return user

            updated = False
            if username is not None and user.username != username:
                user.username = username
                updated = True
            if first_name is not None and user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if last_name is not None and user.last_name != last_name:
                user.last_name = last_name
                updated = True
            if acquisition_source and not user.acquisition_source:
                user.acquisition_source = acquisition_source
                user.acquisition_recorded_at = recorded_at
                updated = True
            if user.credits_status is None:
                user.credits_status = CREDITS_STATUS_NO_CREDITS
                updated = True
            if user.usage_left is None and not user.is_active and user.credits_status != CREDITS_STATUS_ACTIVE:
                user.usage_left = 0
                updated = True
            if updated:
                session.commit()
                session.refresh(user)
            return user

    def _get_or_create_user_in_session(self, session, user_id: int) -> User:
        user = session.query(User).filter(User.user_id == user_id).first()
        if user:
            return user
        user = User(
            user_id=user_id,
            is_active=False,
            credits_status=CREDITS_STATUS_NO_CREDITS,
            usage_left=0,
        )
        session.add(user)
        session.flush()
        return user

    def _record_user_flow_event_sync(
        self,
        user_id: int,
        event_type: str,
        screen_key: str | None,
        action_key: str | None,
        source: str | None,
        meta: dict[str, object] | None,
        update_last_screen: bool,
    ) -> None:
        event_name = str(event_type or "").strip()
        normalized_screen = str(screen_key or "").strip() or None
        normalized_action = str(action_key or "").strip() or None
        normalized_source = str(source or "").strip() or None
        if not user_id or not event_name:
            return
        if normalized_screen is None and normalized_action is None:
            return
        with self._session_factory() as session:
            user = self._get_or_create_user_in_session(session, int(user_id))
            now = utcnow()
            if update_last_screen and normalized_screen:
                user.last_screen_key = normalized_screen
                user.last_screen_at = now
            event = UserFlowEvent(
                user_id=int(user_id),
                event_type=event_name[:32],
                screen_key=(normalized_screen[:64] if normalized_screen else None),
                action_key=(normalized_action[:128] if normalized_action else None),
                source=(normalized_source[:64] if normalized_source else None),
                meta_json=(
                    json.dumps(meta, ensure_ascii=False, sort_keys=True)
                    if isinstance(meta, dict)
                    else None
                ),
                created_at=now,
            )
            session.add(event)
            session.commit()

    def _add_user_sync(
        self, user_id: int, days: int | None, requests: int | None
    ) -> User | None:
        # `days` is kept for backward-compatible admin command format and ignored.
        _ = days
        with self._session_factory() as session:
            granted_credits: int | None = None
            user = (
                session.query(User)
                .filter(User.user_id == user_id)
                .with_for_update()
                .first()
            )
            if not user:
                user = User(
                    user_id=user_id,
                    is_active=False,
                    credits_status=CREDITS_STATUS_NO_CREDITS,
                    usage_left=0,
                )
                session.add(user)
                session.flush()

            if requests and requests > 0:
                # Credits-based mode should always be finite and must disable manual unlimited access.
                user.is_active = False
                base = 0 if user.usage_left is None else max(int(user.usage_left), 0)
                user.usage_left = base + int(requests)
                user.credits_status = CREDITS_STATUS_ACTIVE
                granted_credits = int(requests)
            else:
                user.is_active = True
                if user.credits_status != CREDITS_STATUS_ACTIVE:
                    user.credits_status = CREDITS_STATUS_ACTIVE

            session.commit()
            session.refresh(user)
            if granted_credits and granted_credits > 0:
                self._record_billing_event_sync(
                    provider="telegram_stars",
                    event_type="admin_credit_grant",
                    user_id=user_id,
                    payment_id=None,
                    provider_payment_id=None,
                    telegram_payment_charge_id=None,
                    currency=None,
                    stars_amount=None,
                    credits_amount=granted_credits,
                    reason="whitelist_add",
                    meta={"source": "admin_command"},
                )
            return user

    def _remove_user_sync(self, user_id: int) -> User | None:
        with self._session_factory() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                return None
            user.is_active = False
            user.usage_left = 0
            user.credits_status = CREDITS_STATUS_NO_CREDITS
            session.commit()
            session.refresh(user)
            return user

    def _get_status_sync(self, user_id: int) -> dict:
        with self._session_factory() as session:
            user = session.query(User).filter(User.user_id == user_id).first()
            if not user:
                return {"whitelisted": False, "reason": "not_found", "expires_at": None}

            if user.is_active:
                return {
                    "whitelisted": True,
                    "reason": "manual",
                    "expires_at": None,
                    "remaining_requests": None,
                }

            if user.usage_left is None and user.credits_status == CREDITS_STATUS_ACTIVE:
                return {
                    "whitelisted": True,
                    "reason": "ok",
                    "expires_at": None,
                    "remaining_requests": None,
                }

            remaining = max(int(user.usage_left or 0), 0)
            if remaining > 0:
                if user.credits_status != CREDITS_STATUS_ACTIVE:
                    user.credits_status = CREDITS_STATUS_ACTIVE
                    session.commit()
                return {
                    "whitelisted": True,
                    "reason": "ok",
                    "expires_at": None,
                    "remaining_requests": remaining,
                }

            reason = (
                "exhausted"
                if user.credits_status == CREDITS_STATUS_EXHAUSTED
                else "insufficient_credits"
            )
            return {
                "whitelisted": False,
                "reason": reason,
                "expires_at": None,
                "remaining_requests": 0,
            }

    def _record_request_sync(self, user_id: int, count: int) -> User | None:
        count = max(int(count or 0), 0)
        with self._session_factory() as session:
            user = (
                session.query(User)
                .filter(User.user_id == user_id)
                .with_for_update()
                .first()
            )
            if not user:
                return None
            if count == 0:
                return user
            user.usage_count = (user.usage_count or 0) + count
            user.last_request_at = utcnow()

            if not user.is_active and user.usage_left is not None:
                remaining = max(int(user.usage_left or 0) - count, 0)
                user.usage_left = remaining
                user.credits_status = (
                    CREDITS_STATUS_ACTIVE if remaining > 0 else CREDITS_STATUS_EXHAUSTED
                )

            session.commit()
            session.refresh(user)
            return user

    def _reserve_units_sync(self, user_id: int, units: int) -> dict:
        units = max(int(units or 0), 0)
        if units <= 0:
            return {
                "allowed": False,
                "reason": "invalid_units",
                "remaining_requests": None,
            }

        with self._session_factory() as session:
            user = (
                session.query(User)
                .filter(User.user_id == user_id)
                .with_for_update()
                .first()
            )
            if not user:
                return {
                    "allowed": False,
                    "reason": "not_found",
                    "remaining_requests": None,
                }

            now = utcnow()
            if user.is_active:
                user.usage_count = (user.usage_count or 0) + units
                user.last_request_at = now
                session.commit()
                logger.info(
                    "reserve_units user_id=%s units=%s allowed=true remaining=unlimited source=manual",
                    user_id,
                    units,
                )
                return {
                    "allowed": True,
                    "reason": "ok",
                    "remaining_requests": None,
                }

            if user.usage_left is None:
                user.usage_count = (user.usage_count or 0) + units
                user.last_request_at = now
                user.credits_status = CREDITS_STATUS_ACTIVE
                session.commit()
                logger.info(
                    "reserve_units user_id=%s units=%s allowed=true remaining=unlimited source=credits",
                    user_id,
                    units,
                )
                return {
                    "allowed": True,
                    "reason": "ok",
                    "remaining_requests": None,
                }

            remaining = max(int(user.usage_left or 0), 0)
            if remaining < units:
                logger.info(
                    "reserve_units user_id=%s units=%s allowed=false reason=insufficient remaining=%s",
                    user_id,
                    units,
                    remaining,
                )
                if user.credits_status != CREDITS_STATUS_EXHAUSTED and remaining == 0:
                    user.credits_status = CREDITS_STATUS_EXHAUSTED
                    session.commit()
                return {
                    "allowed": False,
                    "reason": "insufficient_credits",
                    "remaining_requests": remaining,
                }

            remaining_after = remaining - units
            user.usage_left = remaining_after
            user.usage_count = (user.usage_count or 0) + units
            user.last_request_at = now
            user.credits_status = (
                CREDITS_STATUS_ACTIVE if remaining_after > 0 else CREDITS_STATUS_EXHAUSTED
            )
            session.commit()
            self._record_billing_event_sync(
                provider="telegram_stars",
                event_type="credits_spent",
                user_id=user_id,
                payment_id=None,
                provider_payment_id=None,
                telegram_payment_charge_id=None,
                currency=None,
                stars_amount=None,
                credits_amount=int(units),
                reason=None,
                meta={"remaining_after": remaining_after},
            )
            logger.info(
                "reserve_units user_id=%s units=%s allowed=true remaining=%s",
                user_id,
                units,
                remaining_after,
            )
            return {
                "allowed": True,
                "reason": "ok",
                "remaining_requests": remaining_after,
            }

    def _reset_quota_sync(self, user_id: int) -> User | None:
        with self._session_factory() as session:
            user = (
                session.query(User)
                .filter(User.user_id == user_id)
                .with_for_update()
                .first()
            )
            if not user:
                return None
            # Reset should always clear any manual unlimited access.
            user.is_active = False
            user.usage_left = 0
            user.credits_status = CREDITS_STATUS_NO_CREDITS
            session.commit()
            session.refresh(user)
            return user

    def _create_stars_payment_intent_sync(
        self,
        user_id: int,
        credits: int,
        stars_amount: int,
        promo_reservation_id: str | None,
        promo_code_id: str | None,
        stars_original: int | None,
        discount_stars: int | None,
    ) -> dict:
        credits_amount = int(credits or 0)
        final_stars = int(stars_amount or 0)
        promo_reservation_uuid = self._parse_uuid(promo_reservation_id)
        promo_code_uuid = self._parse_uuid(promo_code_id)
        original_stars = int(stars_original or final_stars)
        discount_value = int(discount_stars or 0)
        promo_enabled = any(
            [
                promo_reservation_id,
                promo_code_id,
                stars_original is not None,
                discount_stars is not None,
            ]
        )
        if credits_amount <= 0 or final_stars <= 0:
            return {"status": "invalid"}
        if promo_enabled:
            if promo_reservation_uuid is None or promo_code_uuid is None:
                return {"status": "invalid_promocode", "reason": "invalid_promocode_identifiers"}
            if original_stars <= 0 or discount_value <= 0:
                return {"status": "invalid_promocode", "reason": "invalid_promocode_amounts"}
            if original_stars - discount_value != final_stars:
                return {"status": "invalid_promocode", "reason": "promocode_amount_mismatch"}

        with self._session_factory() as session:
            now = utcnow()
            promo_usage: PromocodeUsage | None = None
            promo_record: Promocode | None = None
            if promo_enabled:
                expired = self._expire_promocode_reservations_sync(
                    session=session,
                    now=now,
                    reservation_id=promo_reservation_uuid,
                    user_id=int(user_id),
                )
                promo_usage = (
                    session.query(PromocodeUsage)
                    .filter(PromocodeUsage.id == promo_reservation_uuid)
                    .with_for_update()
                    .first()
                )
                if promo_usage is None:
                    if expired > 0:
                        session.commit()
                    return {"status": "invalid_promocode", "reason": "promocode_reservation_not_found"}
                if int(promo_usage.user_id or 0) != int(user_id):
                    return {"status": "invalid_promocode", "reason": "promocode_user_mismatch"}
                if promo_usage.code_id != promo_code_uuid:
                    return {"status": "invalid_promocode", "reason": "promocode_code_mismatch"}
                if promo_usage.status != PROMO_USAGE_STATUS_RESERVED:
                    return {"status": "invalid_promocode", "reason": "promocode_not_reserved"}
                if promo_usage.expires_at and promo_usage.expires_at <= now:
                    self._mark_promocode_usage_released(
                        usage=promo_usage,
                        now=now,
                        reason="checkout_expired",
                    )
                    session.commit()
                    return {"status": "invalid_promocode", "reason": "promocode_reservation_expired"}
                if (
                    int(promo_usage.credits_amount or 0) != credits_amount
                    or int(Decimal(promo_usage.price_original or 0)) != original_stars
                    or int(Decimal(promo_usage.discount_amount or 0)) != discount_value
                    or int(Decimal(promo_usage.price_final or 0)) != final_stars
                ):
                    return {"status": "invalid_promocode", "reason": "promocode_checkout_mismatch"}
                promo_record = (
                    session.query(Promocode)
                    .filter(Promocode.id == promo_code_uuid)
                    .with_for_update()
                    .first()
                )
                if promo_record is None:
                    return {"status": "invalid_promocode", "reason": "promocode_not_found"}

            user = (
                session.query(User)
                .filter(User.user_id == int(user_id))
                .with_for_update()
                .first()
            )
            if user is None:
                user = User(
                    user_id=int(user_id),
                    is_active=False,
                    credits_status=CREDITS_STATUS_NO_CREDITS,
                    usage_left=0,
                )
                session.add(user)
                session.flush()

            payment = Payment(
                user_id=int(user_id),
                promocode_id=(promo_record.id if promo_record is not None else None),
                price_original=Decimal(original_stars if promo_enabled else final_stars),
                discount_amount=Decimal(discount_value if promo_enabled else 0),
                price_final=Decimal(final_stars),
                currency="XTR",
                status="pending",
                provider=PROVIDER_STARS,
                provider_payment_id=None,
                telegram_payment_charge_id=None,
                credits_amount=credits_amount,
                paid_at=None,
            )
            session.add(payment)
            session.flush()
            if promo_usage is not None:
                promo_usage.payment_id = payment.id
            session.commit()
            session.refresh(payment)

            self._record_billing_event_sync(
                provider=PROVIDER_STARS,
                event_type="stars_payment_created",
                user_id=int(user_id),
                payment_id=str(payment.id),
                provider_payment_id=None,
                telegram_payment_charge_id=None,
                currency="XTR",
                stars_amount=final_stars,
                credits_amount=credits_amount,
                reason=None,
                meta={
                    "status": payment.status,
                    "price_original": str(original_stars if promo_enabled else final_stars),
                    "discount_amount": str(discount_value if promo_enabled else 0),
                    "price_final": str(final_stars),
                    "promocode_id": str(promo_record.id) if promo_record is not None else None,
                    "promocode_reservation_id": (
                        str(promo_usage.id) if promo_usage is not None else None
                    ),
                },
            )
            return {
                "status": "ok",
                "payment_id": str(payment.id),
                "credits": credits_amount,
                "stars": final_stars,
            }

    def _mark_stars_payment_invoice_sent_sync(
        self,
        payment_id: str,
        invoice_meta: dict[str, object] | None = None,
    ) -> dict:
        payment_uuid = self._parse_payment_uuid(str(payment_id or "").strip())
        if payment_uuid is None:
            return {"status": "invalid_payment_id"}
        with self._session_factory() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == payment_uuid, Payment.provider == PROVIDER_STARS)
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if payment.status != "pending":
                return {"status": "not_pending", "payment_status": payment.status}
            payment.status = "invoice_sent"
            session.commit()
            self._record_billing_event_sync(
                provider=PROVIDER_STARS,
                event_type="stars_invoice_sent",
                user_id=int(payment.user_id),
                payment_id=str(payment.id),
                provider_payment_id=payment.provider_payment_id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
                currency=payment.currency,
                stars_amount=int(payment.price_final or 0),
                credits_amount=int(payment.credits_amount or 0),
                reason=None,
                meta=invoice_meta if isinstance(invoice_meta, dict) else None,
            )
            return {"status": "ok"}

    def _mark_stars_payment_failed_sync(
        self,
        payment_id: str,
        reason: str,
        error_meta: dict[str, object] | None = None,
    ) -> dict:
        payment_uuid = self._parse_payment_uuid(str(payment_id or "").strip())
        failure_reason = str(reason or "invoice_failed").strip()[:64] or "invoice_failed"
        if payment_uuid is None:
            return {"status": "invalid_payment_id"}
        with self._session_factory() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == payment_uuid, Payment.provider == PROVIDER_STARS)
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if payment.status not in {"pending", "invoice_sent"}:
                return {"status": "not_pending", "payment_status": payment.status}
            payment.status = "failed"
            self._release_promocode_for_unpaid_payment_sync(
                session=session,
                payment=payment,
                now=utcnow(),
                reason=f"stars_{failure_reason}",
            )
            session.commit()
            self._record_billing_event_sync(
                provider=PROVIDER_STARS,
                event_type="stars_payment_failed",
                user_id=int(payment.user_id),
                payment_id=str(payment.id),
                provider_payment_id=payment.provider_payment_id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
                currency=payment.currency,
                stars_amount=int(payment.price_final or 0),
                credits_amount=int(payment.credits_amount or 0),
                reason=failure_reason,
                meta=error_meta if isinstance(error_meta, dict) else None,
            )
            return {"status": "ok"}

    def _validate_stars_checkout_intent_sync(
        self,
        payment_id: str,
        user_id: int,
        credits: int,
        stars_amount: int,
    ) -> dict:
        payment_uuid = self._parse_payment_uuid(str(payment_id or "").strip())
        if payment_uuid is None:
            return {"status": "invalid_payment_id"}
        with self._session_factory() as session:
            now = utcnow()
            payment = (
                session.query(Payment)
                .filter(Payment.id == payment_uuid, Payment.provider == PROVIDER_STARS)
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if int(payment.user_id or 0) != int(user_id):
                return {"status": "user_mismatch"}
            if int(payment.credits_amount or 0) != int(credits or 0):
                return {"status": "credits_mismatch"}
            if int(payment.price_final or 0) != int(stars_amount or 0):
                return {"status": "amount_mismatch"}
            if payment.promocode_id is not None:
                usage = (
                    session.query(PromocodeUsage)
                    .filter(
                        PromocodeUsage.payment_id == payment.id,
                        PromocodeUsage.code_id == payment.promocode_id,
                        PromocodeUsage.status == PROMO_USAGE_STATUS_RESERVED,
                    )
                    .with_for_update()
                    .first()
                )
                if usage is None:
                    return {"status": "promo_not_reserved"}
                if usage.expires_at and usage.expires_at <= now:
                    self._mark_promocode_usage_released(
                        usage=usage,
                        now=now,
                        reason="checkout_expired",
                    )
                    session.commit()
                    return {"status": "promo_reservation_expired"}
                if (
                    int(usage.credits_amount or 0) != int(payment.credits_amount or 0)
                    or int(Decimal(usage.price_original or 0)) != int(Decimal(payment.price_original or 0))
                    or int(Decimal(usage.discount_amount or 0)) != int(Decimal(payment.discount_amount or 0))
                    or int(Decimal(usage.price_final or 0)) != int(Decimal(payment.price_final or 0))
                ):
                    return {"status": "promo_checkout_mismatch"}
            if payment.status in {"paid", "refunded"}:
                return {"status": "already_finalized", "payment_status": payment.status}
            if payment.status not in {"pending", "invoice_sent"}:
                return {"status": "invalid_state", "payment_status": payment.status}
            return {"status": "ok", "payment_status": payment.status}

    def _apply_stars_payment_sync(
        self,
        user_id: int,
        credits: int,
        stars_amount: int,
        provider_payment_id: str,
        telegram_payment_charge_id: str | None,
        promo_reservation_id: str | None,
        promo_code_id: str | None,
        stars_original: int | None,
        discount_stars: int | None,
        checkout_payment_id: str | None = None,
    ) -> dict:
        credits = int(credits or 0)
        stars_amount = int(stars_amount or 0)
        provider_pid = str(provider_payment_id or "").strip()
        checkout_uuid = self._parse_payment_uuid(str(checkout_payment_id or "").strip())
        telegram_charge_id = str(telegram_payment_charge_id or "").strip() or None
        promo_reservation_uuid = self._parse_uuid(promo_reservation_id)
        promo_code_uuid = self._parse_uuid(promo_code_id)
        promo_stars_original = int(stars_original or 0)
        promo_discount_stars = int(discount_stars or 0)
        promo_enabled = any(
            [
                promo_reservation_id,
                promo_code_id,
                stars_original is not None,
                discount_stars is not None,
            ]
        )
        if credits <= 0 or stars_amount <= 0 or not provider_pid:
            return {"status": "invalid", "remaining_requests": None}
        if promo_enabled:
            if promo_reservation_uuid is None or promo_code_uuid is None:
                return {"status": "invalid_promocode", "reason": "invalid_promocode_identifiers"}
            if promo_stars_original <= 0 or promo_discount_stars <= 0:
                return {"status": "invalid_promocode", "reason": "invalid_promocode_amounts"}
            if promo_stars_original - promo_discount_stars != stars_amount:
                return {"status": "invalid_promocode", "reason": "promocode_amount_mismatch"}

        with self._session_factory() as session:
            now = utcnow()
            existing = (
                session.query(Payment)
                .filter(
                    Payment.provider == PROVIDER_STARS,
                    Payment.provider_payment_id == provider_pid,
                )
                .first()
            )
            if existing:
                user = session.query(User).filter(User.user_id == user_id).first()
                remaining = None
                if user and not user.is_active:
                    if user.usage_left is not None:
                        remaining = max(int(user.usage_left or 0), 0)
                self._record_billing_event_sync(
                    provider=PROVIDER_STARS,
                    event_type="stars_payment_duplicate",
                    user_id=user_id,
                    payment_id=str(existing.id),
                    provider_payment_id=provider_pid,
                    telegram_payment_charge_id=telegram_charge_id,
                    currency="XTR",
                    stars_amount=stars_amount,
                    credits_amount=credits,
                    reason="duplicate_provider_payment_id",
                    meta=None,
                )
                logger.info(
                    "stars_payment_duplicate user_id=%s payment_id=%s credits=%s stars=%s telegram_charge_id=%s",
                    user_id,
                    provider_pid,
                    credits,
                    stars_amount,
                    telegram_charge_id,
                )
                return {
                    "status": "duplicate",
                    "remaining_requests": remaining,
                }

            user = (
                session.query(User)
                .filter(User.user_id == user_id)
                .with_for_update()
                .first()
            )
            if not user:
                user = User(
                    user_id=user_id,
                    is_active=False,
                    credits_status=CREDITS_STATUS_NO_CREDITS,
                    usage_left=0,
                )
                session.add(user)
                session.flush()

            remaining_after = None
            promo_usage: PromocodeUsage | None = None
            promo_record: Promocode | None = None
            payment: Payment | None = None

            if checkout_uuid is not None:
                payment = (
                    session.query(Payment)
                    .filter(Payment.id == checkout_uuid, Payment.provider == PROVIDER_STARS)
                    .with_for_update()
                    .first()
                )
                if payment is None:
                    return {"status": "invalid_checkout_intent", "reason": "checkout_not_found"}
                if int(payment.user_id or 0) != int(user_id):
                    return {"status": "invalid_checkout_intent", "reason": "checkout_user_mismatch"}
                if int(payment.credits_amount or 0) != credits:
                    return {"status": "invalid_checkout_intent", "reason": "checkout_credits_mismatch"}
                if int(payment.price_final or 0) != stars_amount:
                    return {"status": "invalid_checkout_intent", "reason": "checkout_amount_mismatch"}
                if payment.status == "paid":
                    session.commit()
                    current_remaining = None
                    if not user.is_active and user.usage_left is not None:
                        current_remaining = max(int(user.usage_left or 0), 0)
                    return {"status": "duplicate", "remaining_requests": current_remaining}
                if payment.status == PAYMENT_STATUS_REFUNDED:
                    return {"status": "invalid_checkout_intent", "reason": "checkout_refunded"}
                if payment.status not in {"pending", "invoice_sent"}:
                    return {
                        "status": "invalid_checkout_intent",
                        "reason": f"checkout_invalid_state_{payment.status}",
                    }
                if payment.promocode_id is not None:
                    promo_usage = (
                        session.query(PromocodeUsage)
                        .filter(
                            PromocodeUsage.payment_id == payment.id,
                            PromocodeUsage.status == PROMO_USAGE_STATUS_RESERVED,
                        )
                        .with_for_update()
                        .first()
                    )
                    if promo_usage is not None:
                        promo_record = (
                            session.query(Promocode)
                            .filter(Promocode.id == promo_usage.code_id)
                            .with_for_update()
                            .first()
                        )
                        promo_enabled = True
                        promo_stars_original = int(Decimal(promo_usage.price_original or 0))
                        promo_discount_stars = int(Decimal(promo_usage.discount_amount or 0))
            else:
                if promo_enabled:
                    expired = self._expire_promocode_reservations_sync(
                        session=session,
                        now=now,
                        reservation_id=promo_reservation_uuid,
                        user_id=int(user_id),
                    )
                    promo_usage = (
                        session.query(PromocodeUsage)
                        .filter(PromocodeUsage.id == promo_reservation_uuid)
                        .with_for_update()
                        .first()
                    )
                    if promo_usage is None:
                        if expired > 0:
                            session.commit()
                        return {"status": "invalid_promocode", "reason": "promocode_reservation_not_found"}
                    if int(promo_usage.user_id or 0) != int(user_id):
                        return {"status": "invalid_promocode", "reason": "promocode_user_mismatch"}
                    if promo_usage.code_id != promo_code_uuid:
                        return {"status": "invalid_promocode", "reason": "promocode_code_mismatch"}
                    if promo_usage.status != PROMO_USAGE_STATUS_RESERVED:
                        return {"status": "invalid_promocode", "reason": "promocode_not_reserved"}
                    if promo_usage.expires_at and promo_usage.expires_at <= now:
                        self._mark_promocode_usage_released(
                            usage=promo_usage,
                            now=now,
                            reason="checkout_expired",
                        )
                        session.commit()
                        return {"status": "invalid_promocode", "reason": "promocode_reservation_expired"}

                    expected_credits = int(promo_usage.credits_amount or 0)
                    expected_original = int(Decimal(promo_usage.price_original or 0))
                    expected_discount = int(Decimal(promo_usage.discount_amount or 0))
                    expected_final = int(Decimal(promo_usage.price_final or 0))
                    if (
                        expected_credits != credits
                        or expected_original != promo_stars_original
                        or expected_discount != promo_discount_stars
                        or expected_final != stars_amount
                    ):
                        return {"status": "invalid_promocode", "reason": "promocode_checkout_mismatch"}
                    promo_record = (
                        session.query(Promocode)
                        .filter(Promocode.id == promo_code_uuid)
                        .with_for_update()
                        .first()
                    )
                    if promo_record is None:
                        return {"status": "invalid_promocode", "reason": "promocode_not_found"}

                payment = Payment(
                    user_id=user_id,
                    promocode_id=(promo_record.id if promo_record is not None else None),
                    price_original=Decimal(promo_stars_original if promo_enabled else stars_amount),
                    discount_amount=Decimal(promo_discount_stars if promo_enabled else 0),
                    price_final=Decimal(stars_amount),
                    currency="XTR",
                    status="pending",
                    provider=PROVIDER_STARS,
                    provider_payment_id=None,
                    telegram_payment_charge_id=None,
                    credits_amount=credits,
                    paid_at=None,
                )
                session.add(payment)
                session.flush()
                if promo_usage is not None:
                    promo_usage.payment_id = payment.id

            if not user.is_active:
                base = 0 if user.usage_left is None else max(int(user.usage_left), 0)
                user.usage_left = base + credits
                user.credits_status = CREDITS_STATUS_ACTIVE
                remaining_after = int(user.usage_left or 0)

            payment.provider_payment_id = provider_pid
            payment.telegram_payment_charge_id = telegram_charge_id
            payment.status = "paid"
            payment.paid_at = now
            if payment.price_original is None:
                payment.price_original = Decimal(promo_stars_original if promo_enabled else stars_amount)
            if payment.discount_amount is None:
                payment.discount_amount = Decimal(promo_discount_stars if promo_enabled else 0)
            payment.price_final = Decimal(stars_amount)
            payment.credits_amount = credits

            if promo_usage is not None:
                promo_usage.status = PROMO_USAGE_STATUS_REDEEMED
                promo_usage.redeemed_at = now
                promo_usage.used_at = now
                promo_usage.released_at = None
                promo_usage.release_reason = None
            session.commit()
            self._record_billing_event_sync(
                provider=PROVIDER_STARS,
                event_type="stars_payment_paid",
                user_id=user_id,
                payment_id=str(payment.id),
                provider_payment_id=provider_pid,
                telegram_payment_charge_id=telegram_charge_id,
                currency="XTR",
                stars_amount=stars_amount,
                credits_amount=credits,
                reason=None,
                meta={
                    "remaining_after": remaining_after,
                    "promocode_id": str(promo_record.id) if promo_record is not None else None,
                    "promocode_reservation_id": (
                        str(promo_usage.id) if promo_usage is not None else None
                    ),
                    "price_original": promo_stars_original if promo_enabled else stars_amount,
                    "discount_amount": promo_discount_stars if promo_enabled else 0,
                    "price_final": stars_amount,
                },
            )
            logger.info(
                "stars_payment_applied user_id=%s payment_id=%s credits=%s stars=%s promo=%s telegram_charge_id=%s remaining=%s",
                user_id,
                provider_pid,
                credits,
                stars_amount,
                "yes" if promo_enabled else "no",
                telegram_charge_id,
                "unlimited" if remaining_after is None else remaining_after,
            )
            return {
                "status": "applied",
                "remaining_requests": remaining_after,
            }

    def _create_tbank_payment_intent_sync(
        self,
        user_id: int,
        credits: int,
        amount_rub: Decimal,
        promo_reservation_id: str | None,
        promo_code_id: str | None,
        amount_original_rub: Decimal | None,
        discount_rub: Decimal | None,
    ) -> dict:
        credits_amount = int(credits or 0)
        amount = amount_rub if isinstance(amount_rub, Decimal) else Decimal(str(amount_rub or "0"))
        original_amount = (
            amount_original_rub
            if isinstance(amount_original_rub, Decimal)
            else Decimal(str(amount_original_rub or amount))
        )
        discount_amount = (
            discount_rub if isinstance(discount_rub, Decimal) else Decimal(str(discount_rub or "0"))
        )
        promo_reservation_uuid = self._parse_uuid(promo_reservation_id)
        promo_code_uuid = self._parse_uuid(promo_code_id)
        promo_enabled = any([promo_reservation_id, promo_code_id, discount_amount > 0])
        if credits_amount <= 0 or amount <= 0:
            return {"status": "invalid"}
        if promo_enabled:
            if promo_reservation_uuid is None or promo_code_uuid is None:
                return {"status": "invalid_promocode", "reason": "invalid_promocode_identifiers"}
            if original_amount <= 0 or discount_amount <= 0:
                return {"status": "invalid_promocode", "reason": "invalid_promocode_amounts"}
            if (original_amount - discount_amount) != amount:
                return {"status": "invalid_promocode", "reason": "promocode_amount_mismatch"}

        with self._session_factory() as session:
            now = utcnow()
            promo_usage: PromocodeUsage | None = None
            promo_record: Promocode | None = None
            if promo_enabled:
                expired = self._expire_promocode_reservations_sync(
                    session=session,
                    now=now,
                    reservation_id=promo_reservation_uuid,
                    user_id=int(user_id),
                )
                promo_usage = (
                    session.query(PromocodeUsage)
                    .filter(PromocodeUsage.id == promo_reservation_uuid)
                    .with_for_update()
                    .first()
                )
                if promo_usage is None:
                    if expired > 0:
                        session.commit()
                    return {"status": "invalid_promocode", "reason": "promocode_reservation_not_found"}
                if int(promo_usage.user_id or 0) != int(user_id):
                    return {"status": "invalid_promocode", "reason": "promocode_user_mismatch"}
                if promo_usage.code_id != promo_code_uuid:
                    return {"status": "invalid_promocode", "reason": "promocode_code_mismatch"}
                if promo_usage.status != PROMO_USAGE_STATUS_RESERVED:
                    return {"status": "invalid_promocode", "reason": "promocode_not_reserved"}
                if promo_usage.expires_at and promo_usage.expires_at <= now:
                    self._mark_promocode_usage_released(
                        usage=promo_usage,
                        now=now,
                        reason="checkout_expired",
                    )
                    session.commit()
                    return {"status": "invalid_promocode", "reason": "promocode_reservation_expired"}
                if (
                    int(promo_usage.credits_amount or 0) != credits_amount
                    or Decimal(promo_usage.price_original or 0) != original_amount
                    or Decimal(promo_usage.discount_amount or 0) != discount_amount
                    or Decimal(promo_usage.price_final or 0) != amount
                ):
                    return {"status": "invalid_promocode", "reason": "promocode_checkout_mismatch"}
                promo_record = (
                    session.query(Promocode)
                    .filter(Promocode.id == promo_code_uuid)
                    .with_for_update()
                    .first()
                )
                if promo_record is None:
                    return {"status": "invalid_promocode", "reason": "promocode_not_found"}

            user = (
                session.query(User)
                .filter(User.user_id == int(user_id))
                .with_for_update()
                .first()
            )
            if not user:
                user = User(
                    user_id=int(user_id),
                    is_active=False,
                    credits_status=CREDITS_STATUS_NO_CREDITS,
                    usage_left=0,
                )
                session.add(user)
                session.flush()

            payment = Payment(
                user_id=int(user_id),
                promocode_id=(promo_record.id if promo_record is not None else None),
                price_original=original_amount if promo_enabled else amount,
                discount_amount=discount_amount if promo_enabled else Decimal("0"),
                price_final=amount,
                currency="RUB",
                status="pending",
                provider="tbank_sbp",
                provider_payment_id=None,
                telegram_payment_charge_id=None,
                credits_amount=credits_amount,
                paid_at=None,
            )
            session.add(payment)
            session.flush()
            if promo_usage is not None:
                promo_usage.payment_id = payment.id
            session.commit()
            session.refresh(payment)
            self._record_billing_event_sync(
                provider="tbank_sbp",
                event_type="tbank_payment_created",
                user_id=int(user_id),
                payment_id=str(payment.id),
                provider_payment_id=None,
                telegram_payment_charge_id=None,
                currency="RUB",
                stars_amount=int((amount * Decimal("100")).quantize(Decimal("1"))),
                credits_amount=credits_amount,
                reason=None,
                meta={
                    "amount_rub": str(amount),
                    "amount_original_rub": str(original_amount if promo_enabled else amount),
                    "discount_rub": str(discount_amount if promo_enabled else Decimal("0")),
                    "promocode_id": str(promo_record.id) if promo_record is not None else None,
                    "promocode_reservation_id": str(promo_usage.id) if promo_usage is not None else None,
                    "status": payment.status,
                },
            )
            return {
                "status": "ok",
                "payment_id": str(payment.id),
                "amount_rub": str(amount),
                "credits": credits_amount,
            }

    def _mark_tbank_payment_initialized_sync(
        self,
        payment_id: str,
        provider_payment_id: str,
        init_meta: dict[str, object] | None = None,
    ) -> dict:
        payment_uuid = self._parse_payment_uuid(str(payment_id or "").strip())
        provider_id = str(provider_payment_id or "").strip()
        if payment_uuid is None or not provider_id:
            return {"status": "invalid"}
        with self._session_factory() as session:
            payment = (
                session.query(Payment)
                .filter(
                    Payment.id == payment_uuid,
                    Payment.provider == "tbank_sbp",
                    Payment.user_id.is_not(None),
                )
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            payment.provider_payment_id = provider_id
            session.commit()
            self._record_billing_event_sync(
                provider="tbank_sbp",
                event_type="tbank_payment_initialized",
                user_id=int(payment.user_id),
                payment_id=str(payment.id),
                provider_payment_id=provider_id,
                telegram_payment_charge_id=None,
                currency=payment.currency,
                stars_amount=int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1"))),
                credits_amount=int(payment.credits_amount or 0),
                reason=None,
                meta=init_meta if isinstance(init_meta, dict) else None,
            )
            return {"status": "ok"}

    def _mark_tbank_payment_failed_sync(
        self,
        payment_id: str,
        reason: str,
        error_meta: dict[str, object] | None = None,
    ) -> dict:
        payment_uuid = self._parse_payment_uuid(str(payment_id or "").strip())
        failure_reason = str(reason or "init_failed").strip()[:64] or "init_failed"
        if payment_uuid is None:
            return {"status": "invalid"}
        with self._session_factory() as session:
            now = utcnow()
            payment = (
                session.query(Payment)
                .filter(
                    Payment.id == payment_uuid,
                    Payment.provider == "tbank_sbp",
                    Payment.user_id.is_not(None),
                )
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if payment.status != "pending":
                return {"status": "not_pending", "payment_status": payment.status}
            payment.status = "init_failed"
            self._release_promocode_for_unpaid_payment_sync(
                session=session,
                payment=payment,
                now=now,
                reason="payment_init_failed",
            )
            session.commit()
            self._record_billing_event_sync(
                provider="tbank_sbp",
                event_type="tbank_payment_init_failed",
                user_id=int(payment.user_id),
                payment_id=str(payment.id),
                provider_payment_id=payment.provider_payment_id,
                telegram_payment_charge_id=None,
                currency=payment.currency,
                stars_amount=int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1"))),
                credits_amount=int(payment.credits_amount or 0),
                reason=failure_reason,
                meta=error_meta if isinstance(error_meta, dict) else None,
            )
            return {"status": "ok"}

    def _apply_tbank_notification_sync(
        self,
        order_id: str,
        provider_payment_id: str | None,
        status: str | None,
        success: bool,
        amount_kopecks: int | None,
        payload: dict[str, object] | None,
        accept_statuses: set[str] | None,
    ) -> dict:
        order_uuid = self._parse_payment_uuid(str(order_id or "").strip())
        provider_id = str(provider_payment_id or "").strip() or None
        normalized_status = str(status or "").strip().upper()
        accepted = {item.upper() for item in (accept_statuses or {"CONFIRMED", "AUTHORIZED"})}
        refund_like_statuses = {"REFUNDED", "REVERSED", "CANCELED"}
        partial_refund_like_statuses = {"PARTIAL_REFUNDED", "PARTIAL_REVERSED"}
        if order_uuid is None:
            return {"status": "invalid_order_id"}
        with self._session_factory() as session:
            payment = (
                session.query(Payment)
                .filter(
                    Payment.id == order_uuid,
                    Payment.provider == "tbank_sbp",
                    Payment.user_id.is_not(None),
                )
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}

            if provider_id and not payment.provider_payment_id:
                payment.provider_payment_id = provider_id

            expected_kopecks = int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1")))
            if amount_kopecks is not None and int(amount_kopecks) != expected_kopecks:
                session.commit()
                self._record_billing_event_sync(
                    provider="tbank_sbp",
                    event_type="tbank_payment_invalid_amount",
                    user_id=int(payment.user_id),
                    payment_id=str(payment.id),
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    telegram_payment_charge_id=None,
                    currency=payment.currency,
                    stars_amount=int(amount_kopecks),
                    credits_amount=int(payment.credits_amount or 0),
                    reason="amount_mismatch",
                    meta={
                        "expected_kopecks": expected_kopecks,
                        "actual_kopecks": int(amount_kopecks),
                        "status": normalized_status,
                    },
                )
                return {
                    "status": "invalid_amount",
                    "expected_kopecks": expected_kopecks,
                    "actual_kopecks": int(amount_kopecks),
                }

            if normalized_status in partial_refund_like_statuses:
                session.commit()
                self._record_billing_event_sync(
                    provider="tbank_sbp",
                    event_type="tbank_payment_partial_refund_ignored",
                    user_id=int(payment.user_id),
                    payment_id=str(payment.id),
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    telegram_payment_charge_id=None,
                    currency=payment.currency,
                    stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                    credits_amount=int(payment.credits_amount or 0),
                    reason=f"status_{normalized_status}",
                    meta=payload if isinstance(payload, dict) else None,
                )
                return {"status": "partial_refund_ignored", "payment_status": payment.status}

            if normalized_status in refund_like_statuses:
                if payment.status == "refunded":
                    session.commit()
                    self._record_billing_event_sync(
                        provider="tbank_sbp",
                        event_type="tbank_payment_refund_duplicate",
                        user_id=int(payment.user_id),
                        payment_id=str(payment.id),
                        provider_payment_id=provider_id or payment.provider_payment_id,
                        telegram_payment_charge_id=None,
                        currency=payment.currency,
                        stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                        credits_amount=int(payment.credits_amount or 0),
                        reason="duplicate_refund_notification",
                        meta={"status": normalized_status},
                    )
                    return {
                        "status": "duplicate_refund",
                        "payment_status": payment.status,
                    }
                if payment.status in {"pending", "authorized", "confirmed"}:
                    previous_status = payment.status
                    payment.status = "canceled"
                    self._release_promocode_for_unpaid_payment_sync(
                        session=session,
                        payment=payment,
                        now=utcnow(),
                        reason="payment_canceled_before_capture",
                    )
                    session.commit()
                    self._record_billing_event_sync(
                        provider="tbank_sbp",
                        event_type="tbank_payment_canceled",
                        user_id=int(payment.user_id),
                        payment_id=str(payment.id),
                        provider_payment_id=provider_id or payment.provider_payment_id,
                        telegram_payment_charge_id=None,
                        currency=payment.currency,
                        stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                        credits_amount=int(payment.credits_amount or 0),
                        reason=f"status_{normalized_status}",
                        meta={"payment_status_before": previous_status},
                    )
                    return {"status": "canceled", "payment_status": payment.status}
                if payment.status != "paid":
                    session.commit()
                    self._record_billing_event_sync(
                        provider="tbank_sbp",
                        event_type="tbank_payment_refund_ignored",
                        user_id=int(payment.user_id),
                        payment_id=str(payment.id),
                        provider_payment_id=provider_id or payment.provider_payment_id,
                        telegram_payment_charge_id=None,
                        currency=payment.currency,
                        stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                        credits_amount=int(payment.credits_amount or 0),
                        reason=f"non_paid_status_{payment.status}",
                        meta={"status": normalized_status},
                    )
                    return {
                        "status": "refund_ignored",
                        "payment_status": payment.status,
                    }

                user = (
                    session.query(User)
                    .filter(User.user_id == int(payment.user_id))
                    .with_for_update()
                    .first()
                )
                credits_amount = max(int(payment.credits_amount or 0), 0)
                if user is None:
                    payment.status = PAYMENT_STATUS_REFUND_PENDING
                    payment.refund_reason = "tbank_refund_user_not_found"
                    session.commit()
                    self._record_billing_event_sync(
                        provider="tbank_sbp",
                        event_type="tbank_refund_pending",
                        user_id=int(payment.user_id),
                        payment_id=str(payment.id),
                        provider_payment_id=provider_id or payment.provider_payment_id,
                        telegram_payment_charge_id=None,
                        currency=payment.currency,
                        stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                        credits_amount=credits_amount,
                        reason="user_not_found",
                        meta={"status": normalized_status},
                    )
                    return {"status": "refund_pending", "reason": "user_not_found"}

                if user.is_active:
                    payment.status = PAYMENT_STATUS_REFUND_PENDING
                    payment.refund_reason = "tbank_refund_manual_unlimited_user"
                    session.commit()
                    self._record_billing_event_sync(
                        provider="tbank_sbp",
                        event_type="tbank_refund_pending",
                        user_id=int(payment.user_id),
                        payment_id=str(payment.id),
                        provider_payment_id=provider_id or payment.provider_payment_id,
                        telegram_payment_charge_id=None,
                        currency=payment.currency,
                        stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                        credits_amount=credits_amount,
                        reason="manual_unlimited_user",
                        meta={"status": normalized_status},
                    )
                    return {"status": "refund_pending", "reason": "manual_unlimited_user"}

                remaining_before = max(int(user.usage_left or 0), 0)
                if remaining_before < credits_amount:
                    payment.status = PAYMENT_STATUS_REFUND_PENDING
                    payment.refund_reason = "tbank_refund_insufficient_unused_credits"
                    session.commit()
                    self._record_billing_event_sync(
                        provider="tbank_sbp",
                        event_type="tbank_refund_pending",
                        user_id=int(payment.user_id),
                        payment_id=str(payment.id),
                        provider_payment_id=provider_id or payment.provider_payment_id,
                        telegram_payment_charge_id=None,
                        currency=payment.currency,
                        stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                        credits_amount=credits_amount,
                        reason="insufficient_unused_credits",
                        meta={
                            "status": normalized_status,
                            "remaining_before": remaining_before,
                            "required_credits": credits_amount,
                        },
                    )
                    return {
                        "status": "refund_pending",
                        "reason": "insufficient_unused_credits",
                        "remaining_requests": remaining_before,
                        "required_credits": credits_amount,
                    }

                remaining_after = remaining_before - credits_amount
                user.usage_left = remaining_after
                user.credits_status = (
                    CREDITS_STATUS_ACTIVE if remaining_after > 0 else CREDITS_STATUS_EXHAUSTED
                )
                payment.status = PAYMENT_STATUS_REFUNDED
                payment.refunded_at = utcnow()
                payment.refund_reason = f"tbank_webhook_{normalized_status.lower()[:32]}"
                session.commit()
                self._record_billing_event_sync(
                    provider="tbank_sbp",
                    event_type="tbank_payment_refunded",
                    user_id=int(payment.user_id),
                    payment_id=str(payment.id),
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    telegram_payment_charge_id=None,
                    currency=payment.currency,
                    stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                    credits_amount=credits_amount,
                    reason=f"status_{normalized_status}",
                    meta={
                        "remaining_before": remaining_before,
                        "remaining_after": remaining_after,
                    },
                )
                return {
                    "status": "refunded",
                    "payment_id": str(payment.id),
                    "user_id": int(payment.user_id),
                    "remaining_requests": remaining_after,
                    "credits": credits_amount,
                }

            if not success or normalized_status not in accepted:
                if payment.status == "pending":
                    mapped_status = normalized_status.lower() if normalized_status else "failed"
                    payment.status = mapped_status[:32]
                    self._release_promocode_for_unpaid_payment_sync(
                        session=session,
                        payment=payment,
                        now=utcnow(),
                        reason=f"payment_status_{payment.status}",
                    )
                session.commit()
                self._record_billing_event_sync(
                    provider="tbank_sbp",
                    event_type="tbank_payment_status_ignored",
                    user_id=int(payment.user_id),
                    payment_id=str(payment.id),
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    telegram_payment_charge_id=None,
                    currency=payment.currency,
                    stars_amount=int(amount_kopecks) if amount_kopecks is not None else None,
                    credits_amount=int(payment.credits_amount or 0),
                    reason=f"status_{normalized_status or 'unknown'}",
                    meta=payload if isinstance(payload, dict) else None,
                )
                return {"status": "ignored", "payment_status": payment.status}

            if payment.status == "paid":
                self._redeem_promocode_for_payment_sync(
                    session=session,
                    payment=payment,
                    now=utcnow(),
                )
                session.commit()
                self._record_billing_event_sync(
                    provider="tbank_sbp",
                    event_type="tbank_payment_duplicate",
                    user_id=int(payment.user_id),
                    payment_id=str(payment.id),
                    provider_payment_id=provider_id or payment.provider_payment_id,
                    telegram_payment_charge_id=None,
                    currency=payment.currency,
                    stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                    credits_amount=int(payment.credits_amount or 0),
                    reason="duplicate_notification",
                    meta={"status": normalized_status},
                )
                user = session.query(User).filter(User.user_id == int(payment.user_id)).first()
                remaining = None
                if user and not user.is_active and user.usage_left is not None:
                    remaining = max(int(user.usage_left or 0), 0)
                return {
                    "status": "duplicate",
                    "user_id": int(payment.user_id),
                    "remaining_requests": remaining,
                    "credits": int(payment.credits_amount or 0),
                }

            user = (
                session.query(User)
                .filter(User.user_id == int(payment.user_id))
                .with_for_update()
                .first()
            )
            if user is None:
                user = User(
                    user_id=int(payment.user_id),
                    is_active=False,
                    credits_status=CREDITS_STATUS_NO_CREDITS,
                    usage_left=0,
                )
                session.add(user)
                session.flush()
            credits_amount = max(int(payment.credits_amount or 0), 0)
            remaining_after = None
            if not user.is_active:
                base = 0 if user.usage_left is None else max(int(user.usage_left), 0)
                user.usage_left = base + credits_amount
                user.credits_status = CREDITS_STATUS_ACTIVE
                remaining_after = int(user.usage_left or 0)

            payment.status = "paid"
            payment.paid_at = utcnow()
            self._redeem_promocode_for_payment_sync(
                session=session,
                payment=payment,
                now=payment.paid_at,
            )
            session.commit()
            self._record_billing_event_sync(
                provider="tbank_sbp",
                event_type="tbank_payment_paid",
                user_id=int(payment.user_id),
                payment_id=str(payment.id),
                provider_payment_id=provider_id or payment.provider_payment_id,
                telegram_payment_charge_id=None,
                currency=payment.currency,
                stars_amount=int(amount_kopecks) if amount_kopecks is not None else expected_kopecks,
                credits_amount=credits_amount,
                reason=None,
                meta={
                    "remaining_after": remaining_after,
                    "status": normalized_status,
                },
            )
            return {
                "status": "applied",
                "payment_id": str(payment.id),
                "user_id": int(payment.user_id),
                "remaining_requests": remaining_after,
                "credits": credits_amount,
            }

    def _release_promocode_for_unpaid_payment_sync(
        self,
        *,
        session,
        payment: Payment,
        now,
        reason: str,
    ) -> None:
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
        self._mark_promocode_usage_released(
            usage=usage,
            now=now,
            reason=reason,
        )
        session.flush()
        self._record_billing_event_sync(
            provider=payment.provider or PROVIDER_TBANK,
            event_type="promocode_released",
            user_id=int(payment.user_id),
            payment_id=str(payment.id),
            provider_payment_id=payment.provider_payment_id,
            telegram_payment_charge_id=None,
            currency=payment.currency,
            stars_amount=int(Decimal(usage.price_final or 0)),
            credits_amount=int(usage.credits_amount or 0),
            reason=str(reason or "payment_not_completed")[:64],
            meta={
                "reservation_id": str(usage.id),
                "code_id": str(usage.code_id),
            },
        )

    def _redeem_promocode_for_payment_sync(
        self,
        *,
        session,
        payment: Payment,
        now,
    ) -> None:
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

    def _check_promocode_sync(self, user_id: int, code: str) -> dict:
        normalized = self._normalize_promocode_code(code)
        if not normalized:
            return {"status": "invalid", "reason": "empty_code"}
        now = utcnow()
        with self._session_factory() as session:
            expired = self._expire_promocode_reservations_sync(
                session=session,
                now=now,
                user_id=int(user_id),
            )
            if expired > 0:
                session.commit()
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

            if promo.code_amount is not None:
                current_left = self._promo_code_left(promo)
                if current_left <= 0:
                    return {"status": "invalid", "reason": "code_exhausted"}

            if bool(promo.is_new_users_only) and not self._is_user_new_for_promocode(
                session=session,
                user_id=int(user_id),
            ):
                return {"status": "invalid", "reason": "new_users_only"}

            max_uses = int(promo.max_uses_per_user or 0)
            if max_uses > 0:
                used_count = (
                    session.query(func.count(PromocodeUsage.id))
                    .filter(
                        PromocodeUsage.code_id == promo.id,
                        PromocodeUsage.user_id == int(user_id),
                        PromocodeUsage.status == PROMO_USAGE_STATUS_REDEEMED,
                    )
                    .scalar()
                )
                if int(used_count or 0) >= max_uses:
                    return {"status": "invalid", "reason": "max_uses_per_user_reached"}

            discount_type = str(promo.discount_type or "").strip().lower()
            if discount_type not in {"percent", "fixed"}:
                return {"status": "invalid", "reason": "unsupported_discount_type"}

            return {
                "status": "ok",
                "code_id": str(promo.id),
                "code": promo.code_string,
                "discount_type": discount_type,
                "discount_amount": str(promo.discount_amount),
                "code_left": self._promo_code_left(promo),
                "is_new_users_only": bool(promo.is_new_users_only),
                "max_uses_per_user": (
                    int(promo.max_uses_per_user)
                    if promo.max_uses_per_user is not None
                    else None
                ),
                "starts_at": promo.starts_at,
                "ends_at": promo.ends_at,
            }

    def _reserve_promocode_sync(
        self,
        user_id: int,
        code: str,
        credits: int,
        stars_original: int,
        ttl_seconds: int,
        previous_reservation_id: str | None,
        provider: str,
        currency: str,
    ) -> dict:
        normalized = self._normalize_promocode_code(code)
        credits_amount = int(credits or 0)
        original_amount = int(stars_original or 0)
        ttl = max(int(ttl_seconds or DEFAULT_PROMO_RESERVATION_TTL_SECONDS), 60)
        if not normalized:
            return {"status": "invalid", "reason": "empty_code"}
        if credits_amount <= 0 or original_amount <= 0:
            return {"status": "invalid", "reason": "invalid_checkout_amounts"}

        now = utcnow()
        previous_uuid = self._parse_uuid(previous_reservation_id)
        with self._session_factory() as session:
            self._expire_promocode_reservations_sync(session=session, now=now, user_id=int(user_id))
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

            if bool(promo.is_new_users_only) and not self._is_user_new_for_promocode(
                session=session,
                user_id=int(user_id),
            ):
                return {"status": "invalid", "reason": "new_users_only"}

            max_uses = int(promo.max_uses_per_user or 0)
            if max_uses > 0:
                used_count = (
                    session.query(func.count(PromocodeUsage.id))
                    .filter(
                        PromocodeUsage.code_id == promo.id,
                        PromocodeUsage.user_id == int(user_id),
                        PromocodeUsage.status == PROMO_USAGE_STATUS_REDEEMED,
                    )
                    .scalar()
                )
                if int(used_count or 0) >= max_uses:
                    return {"status": "invalid", "reason": "max_uses_per_user_reached"}

            pricing = self._compute_promocode_pricing(promo, original_amount)
            if pricing is None:
                return {"status": "invalid", "reason": "invalid_discount"}

            existing_usage = None
            if previous_uuid is not None:
                existing_usage = (
                    session.query(PromocodeUsage)
                    .filter(
                        PromocodeUsage.id == previous_uuid,
                        PromocodeUsage.user_id == int(user_id),
                        PromocodeUsage.status == PROMO_USAGE_STATUS_RESERVED,
                        PromocodeUsage.payment_id.is_(None),
                    )
                    .with_for_update()
                    .first()
                )
                if existing_usage is not None and existing_usage.code_id != promo.id:
                    existing_usage = None

            self._release_user_active_reservations_sync(
                session=session,
                user_id=int(user_id),
                now=now,
                reason="replaced_before_new_reserve",
                keep_reservation_id=(existing_usage.id if existing_usage is not None else None),
            )

            expires_at = now + timedelta(seconds=ttl)
            if existing_usage is not None:
                existing_usage.reserved_at = now
                existing_usage.expires_at = expires_at
                existing_usage.released_at = None
                existing_usage.release_reason = None
                existing_usage.redeemed_at = None
                existing_usage.used_at = now
                existing_usage.credits_amount = credits_amount
                existing_usage.price_original = Decimal(pricing["stars_original"])
                existing_usage.discount_amount = Decimal(pricing["discount_stars"])
                existing_usage.price_final = Decimal(pricing["stars_final"])
                session.commit()
                self._record_billing_event_sync(
                    provider=str(provider or PROVIDER_STARS),
                    event_type="promocode_reserved",
                    user_id=int(user_id),
                    payment_id=None,
                    provider_payment_id=None,
                    telegram_payment_charge_id=None,
                    currency=str(currency or "XTR"),
                    stars_amount=int(pricing["stars_final"]),
                    credits_amount=credits_amount,
                    reason=promo.code_string,
                    meta={
                        "reservation_id": str(existing_usage.id),
                        "code_id": str(promo.id),
                        "code": promo.code_string,
                        "stars_original": int(pricing["stars_original"]),
                        "discount_stars": int(pricing["discount_stars"]),
                        "stars_final": int(pricing["stars_final"]),
                        "expires_at": expires_at.isoformat(),
                        "reused_existing": True,
                    },
                )
                return {
                    "status": "ok",
                    "reservation_id": str(existing_usage.id),
                    "code_id": str(promo.id),
                    "code": promo.code_string,
                    "credits": credits_amount,
                    "stars_original": int(pricing["stars_original"]),
                    "discount_stars": int(pricing["discount_stars"]),
                    "stars_final": int(pricing["stars_final"]),
                    "expires_at": expires_at.isoformat(),
                }

            if promo.code_amount is not None:
                current_left = self._promo_code_left(promo)
                if current_left <= 0:
                    return {"status": "invalid", "reason": "code_exhausted"}
                promo.code_left = current_left - 1

            usage = PromocodeUsage(
                code_id=promo.id,
                user_id=int(user_id),
                status=PROMO_USAGE_STATUS_RESERVED,
                reserved_at=now,
                expires_at=expires_at,
                release_reason=None,
                credits_amount=credits_amount,
                price_original=Decimal(pricing["stars_original"]),
                discount_amount=Decimal(pricing["discount_stars"]),
                price_final=Decimal(pricing["stars_final"]),
                used_at=now,
            )
            session.add(usage)
            session.commit()
            self._record_billing_event_sync(
                provider=str(provider or PROVIDER_STARS),
                event_type="promocode_reserved",
                user_id=int(user_id),
                payment_id=None,
                provider_payment_id=None,
                telegram_payment_charge_id=None,
                currency=str(currency or "XTR"),
                stars_amount=int(pricing["stars_final"]),
                credits_amount=credits_amount,
                reason=promo.code_string,
                meta={
                    "reservation_id": str(usage.id),
                    "code_id": str(promo.id),
                    "code": promo.code_string,
                    "stars_original": int(pricing["stars_original"]),
                    "discount_stars": int(pricing["discount_stars"]),
                    "stars_final": int(pricing["stars_final"]),
                    "expires_at": expires_at.isoformat(),
                },
            )
            return {
                "status": "ok",
                "reservation_id": str(usage.id),
                "code_id": str(promo.id),
                "code": promo.code_string,
                "credits": credits_amount,
                "stars_original": int(pricing["stars_original"]),
                "discount_stars": int(pricing["discount_stars"]),
                "stars_final": int(pricing["stars_final"]),
                "expires_at": expires_at.isoformat(),
            }

    def _release_promocode_reservation_sync(
        self,
        reservation_id: str,
        user_id: int,
        reason: str,
        provider: str,
        currency: str,
    ) -> dict:
        reservation_uuid = self._parse_uuid(reservation_id)
        if reservation_uuid is None:
            return {"status": "invalid_reservation_id"}
        now = utcnow()
        with self._session_factory() as session:
            expired = self._expire_promocode_reservations_sync(
                session=session,
                now=now,
                user_id=int(user_id),
            )
            usage = (
                session.query(PromocodeUsage)
                .filter(PromocodeUsage.id == reservation_uuid)
                .with_for_update()
                .first()
            )
            if usage is None:
                if expired > 0:
                    session.commit()
                return {"status": "not_found"}
            if int(usage.user_id or 0) != int(user_id):
                if expired > 0:
                    session.commit()
                return {"status": "forbidden"}
            if usage.status == PROMO_USAGE_STATUS_REDEEMED:
                if expired > 0:
                    session.commit()
                return {"status": "already_redeemed"}
            if usage.status in {PROMO_USAGE_STATUS_RELEASED, PROMO_USAGE_STATUS_EXPIRED}:
                if expired > 0:
                    session.commit()
                return {"status": "already_released"}
            self._mark_promocode_usage_released(
                usage=usage,
                now=now,
                reason=str(reason or "manual_release")[:64],
            )
            session.commit()
            self._record_billing_event_sync(
                provider=str(provider or PROVIDER_STARS),
                event_type="promocode_released",
                user_id=int(user_id),
                payment_id=None,
                provider_payment_id=None,
                telegram_payment_charge_id=None,
                currency=str(currency or "XTR"),
                stars_amount=int(usage.price_final or 0),
                credits_amount=int(usage.credits_amount or 0),
                reason=str(reason or "manual_release")[:64],
                meta={
                    "reservation_id": str(usage.id),
                    "code_id": str(usage.code_id),
                },
            )
            return {"status": "released"}

    def _validate_promocode_reservation_sync(
        self,
        reservation_id: str,
        user_id: int,
        promo_code_id: str,
        credits: int,
        stars_original: int,
        discount_stars: int,
        stars_final: int,
    ) -> dict:
        reservation_uuid = self._parse_uuid(reservation_id)
        promo_uuid = self._parse_uuid(promo_code_id)
        if reservation_uuid is None or promo_uuid is None:
            return {"status": "invalid", "reason": "invalid_identifiers"}
        expected_credits = int(credits or 0)
        expected_original = int(stars_original or 0)
        expected_discount = int(discount_stars or 0)
        expected_final = int(stars_final or 0)
        if (
            expected_credits <= 0
            or expected_original <= 0
            or expected_discount <= 0
            or expected_final <= 0
        ):
            return {"status": "invalid", "reason": "invalid_amounts"}
        if expected_original - expected_discount != expected_final:
            return {"status": "invalid", "reason": "amount_mismatch"}

        now = utcnow()
        with self._session_factory() as session:
            expired = self._expire_promocode_reservations_sync(
                session=session,
                now=now,
                reservation_id=reservation_uuid,
                user_id=int(user_id),
            )
            usage = (
                session.query(PromocodeUsage)
                .filter(PromocodeUsage.id == reservation_uuid)
                .with_for_update()
                .first()
            )
            if usage is None:
                if expired > 0:
                    session.commit()
                return {"status": "invalid", "reason": "reservation_not_found"}
            if int(usage.user_id or 0) != int(user_id):
                if expired > 0:
                    session.commit()
                return {"status": "invalid", "reason": "user_mismatch"}
            if usage.code_id != promo_uuid:
                if expired > 0:
                    session.commit()
                return {"status": "invalid", "reason": "code_mismatch"}
            if usage.status != PROMO_USAGE_STATUS_RESERVED:
                if expired > 0:
                    session.commit()
                return {"status": "invalid", "reason": "reservation_not_active"}
            if usage.expires_at and usage.expires_at <= now:
                self._mark_promocode_usage_released(
                    usage=usage,
                    now=now,
                    reason="checkout_expired",
                )
                session.commit()
                return {"status": "invalid", "reason": "reservation_expired"}

            if (
                int(usage.credits_amount or 0) != expected_credits
                or int(usage.price_original or 0) != expected_original
                or int(usage.discount_amount or 0) != expected_discount
                or int(usage.price_final or 0) != expected_final
            ):
                if expired > 0:
                    session.commit()
                return {"status": "invalid", "reason": "checkout_mismatch"}
            return {"status": "ok"}

    def _release_user_active_reservations_sync(
        self,
        *,
        session,
        user_id: int,
        now,
        reason: str,
        keep_reservation_id: UUID | None = None,
    ) -> None:
        query = (
            session.query(PromocodeUsage)
            .filter(
                PromocodeUsage.user_id == int(user_id),
                PromocodeUsage.status == PROMO_USAGE_STATUS_RESERVED,
                PromocodeUsage.payment_id.is_(None),
            )
            .with_for_update()
        )
        for usage in query.all():
            if keep_reservation_id is not None and usage.id == keep_reservation_id:
                continue
            self._mark_promocode_usage_released(
                usage=usage,
                now=now,
                reason=reason,
            )
        session.flush()

    def _expire_promocode_reservations_sync(
        self,
        *,
        session,
        now,
        reservation_id: UUID | None = None,
        user_id: int | None = None,
    ) -> int:
        query = (
            session.query(PromocodeUsage)
            .filter(
                PromocodeUsage.status == PROMO_USAGE_STATUS_RESERVED,
                PromocodeUsage.expires_at.is_not(None),
                PromocodeUsage.expires_at <= now,
                PromocodeUsage.payment_id.is_(None),
            )
            .with_for_update()
        )
        if reservation_id is not None:
            query = query.filter(PromocodeUsage.id == reservation_id)
        if user_id is not None:
            query = query.filter(PromocodeUsage.user_id == int(user_id))
        expired = query.all()
        if not expired:
            return 0
        for usage in expired:
            self._mark_promocode_usage_released(
                usage=usage,
                now=now,
                reason="ttl_expired",
            )
        session.flush()
        return len(expired)

    def _mark_promocode_usage_released(self, *, usage: PromocodeUsage, now, reason: str) -> None:
        if usage.status != PROMO_USAGE_STATUS_RESERVED:
            return
        promo = usage.promocode
        if promo is not None and promo.code_amount is not None:
            current_left = self._promo_code_left(promo)
            promo.code_left = min(int(promo.code_amount), current_left + 1)
        usage.status = (
            PROMO_USAGE_STATUS_EXPIRED if reason == "ttl_expired" else PROMO_USAGE_STATUS_RELEASED
        )
        usage.released_at = now
        usage.release_reason = str(reason or "released")[:64]

    @staticmethod
    def _normalize_promocode_code(code: str) -> str:
        return "".join(str(code or "").strip().split()).upper()[:64]

    @staticmethod
    def _parse_uuid(value: str | None) -> UUID | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        try:
            return UUID(raw)
        except Exception:
            return None

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
    def _is_user_new_for_promocode(session, user_id: int) -> bool:
        paid_count = (
            session.query(func.count(Payment.id))
            .filter(
                Payment.user_id == int(user_id),
                Payment.provider.in_(BILLING_REPORT_PROVIDERS),
                Payment.paid_at.is_not(None),
            )
            .scalar()
        )
        return int(paid_count or 0) == 0

    @staticmethod
    def _compute_promocode_pricing(
        promo: Promocode,
        stars_original: int,
    ) -> dict[str, int] | None:
        original = int(stars_original or 0)
        if original <= 0:
            return None
        discount_type = str(promo.discount_type or "").strip().lower()
        amount_raw = Decimal(promo.discount_amount or 0)
        if amount_raw <= 0:
            return None
        if discount_type == "percent":
            discount = int(
                (
                    Decimal(original) * amount_raw / Decimal("100")
                ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        elif discount_type == "fixed":
            discount = int(amount_raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            return None
        if discount <= 0:
            return None
        final = original - discount
        if final <= 0:
            return None
        return {
            "stars_original": original,
            "discount_stars": discount,
            "stars_final": final,
        }

    def _record_billing_event_sync(
        self,
        provider: str,
        event_type: str,
        user_id: int | None,
        payment_id: str | None,
        provider_payment_id: str | None,
        telegram_payment_charge_id: str | None,
        currency: str | None,
        stars_amount: int | None,
        provider_amount: Decimal | int | float | str | None = None,
        credits_amount: int | None = None,
        reason: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        provider_name = str(provider or "").strip()
        event_name = str(event_type or "").strip()
        if not provider_name or not event_name:
            return
        with self._session_factory() as session:
            payment_uuid = self._parse_payment_uuid(str(payment_id or "").strip())
            currency_name = str(currency or "").strip() or None
            amount_value = int(stars_amount) if stars_amount is not None else None
            payment_amount_value: Decimal | None = None
            if payment_uuid is not None:
                payment_amount = (
                    session.query(Payment.price_final)
                    .filter(Payment.id == payment_uuid)
                    .first()
                )
                if payment_amount is not None and payment_amount[0] is not None:
                    try:
                        payment_amount_value = Decimal(str(payment_amount[0]))
                    except Exception:
                        payment_amount_value = None

            provider_amount_value: Decimal | None = None
            if provider_amount is not None:
                try:
                    provider_amount_value = Decimal(str(provider_amount)).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                except Exception:
                    provider_amount_value = None

            if amount_value is not None and currency_name == "RUB":
                if payment_amount_value is not None:
                    expected_kopecks = int(
                        (payment_amount_value * Decimal("100")).quantize(
                            Decimal("1"), rounding=ROUND_HALF_UP
                        )
                    )
                    expected_rub_int = int(
                        payment_amount_value.quantize(
                            Decimal("1"), rounding=ROUND_HALF_UP
                        )
                    )
                    if amount_value == expected_kopecks:
                        # Legacy write path that stored kopecks into stars_amount.
                        amount_value = expected_rub_int
                        if provider_amount_value is None:
                            provider_amount_value = payment_amount_value.quantize(
                                Decimal("0.01"), rounding=ROUND_HALF_UP
                            )
                    elif amount_value == expected_rub_int and provider_amount_value is None:
                        provider_amount_value = payment_amount_value.quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    elif provider_amount_value is None:
                        provider_amount_value = (
                            Decimal(amount_value) / Decimal("100")
                        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                elif provider_amount_value is None:
                    provider_amount_value = Decimal(amount_value).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
            elif amount_value is not None and provider_amount_value is None:
                provider_amount_value = Decimal(amount_value).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            event = BillingEvent(
                provider=provider_name,
                event_type=event_name,
                user_id=int(user_id) if user_id is not None else None,
                payment_id=payment_uuid,
                provider_payment_id=str(provider_payment_id or "").strip() or None,
                telegram_payment_charge_id=str(telegram_payment_charge_id or "").strip() or None,
                currency=currency_name,
                stars_amount=amount_value,
                provider_amount=provider_amount_value,
                credits_amount=int(credits_amount) if credits_amount is not None else None,
                reason=str(reason or "").strip() or None,
                meta_json=(
                    json.dumps(meta, ensure_ascii=False, sort_keys=True)
                    if isinstance(meta, dict)
                    else None
                ),
                created_at=utcnow(),
            )
            session.add(event)
            session.commit()

    def _lookback_start(self, days: int) -> object:
        safe_days = max(1, min(int(days or 1), 3650))
        return utcnow() - timedelta(days=safe_days)

    def _get_flow_report_sync(self, days: int, acquisition_source: str | None) -> dict:
        start_at = self._lookback_start(days)
        source_value = str(acquisition_source or "").strip() or None
        with self._session_factory() as session:
            event_query = session.query(UserFlowEvent).filter(UserFlowEvent.created_at >= start_at)
            if source_value:
                event_query = event_query.join(User, User.user_id == UserFlowEvent.user_id).filter(
                    User.acquisition_source == source_value
                )

            users_total = (
                event_query.with_entities(func.count(func.distinct(UserFlowEvent.user_id))).scalar() or 0
            )

            screen_rows = (
                event_query.with_entities(
                    UserFlowEvent.screen_key,
                    func.count(UserFlowEvent.id),
                    func.count(func.distinct(UserFlowEvent.user_id)),
                )
                .filter(
                    UserFlowEvent.event_type == "screen_view",
                    UserFlowEvent.screen_key.isnot(None),
                )
                .group_by(UserFlowEvent.screen_key)
                .all()
            )
            action_rows = (
                event_query.with_entities(
                    UserFlowEvent.action_key,
                    func.count(UserFlowEvent.id),
                    func.count(func.distinct(UserFlowEvent.user_id)),
                )
                .filter(
                    UserFlowEvent.event_type == "action_click",
                    UserFlowEvent.action_key.isnot(None),
                )
                .group_by(UserFlowEvent.action_key)
                .all()
            )

            user_query = session.query(User).filter(User.last_screen_at.isnot(None), User.last_screen_at >= start_at)
            if source_value:
                user_query = user_query.filter(User.acquisition_source == source_value)
            last_screen_rows = (
                user_query.with_entities(User.last_screen_key, func.count(User.user_id))
                .filter(User.last_screen_key.isnot(None))
                .group_by(User.last_screen_key)
                .all()
            )

        return {
            "days": max(int(days or 1), 1),
            "since_utc": start_at.isoformat(),
            "acquisition_source": source_value,
            "users_total": int(users_total),
            "screen_views": [
                {"screen_key": str(key), "views": int(views or 0), "users": int(users or 0)}
                for key, views, users in sorted(screen_rows, key=lambda item: (-int(item[1] or 0), str(item[0] or "")))
            ],
            "action_clicks": [
                {"action_key": str(key), "clicks": int(clicks or 0), "users": int(users or 0)}
                for key, clicks, users in sorted(action_rows, key=lambda item: (-int(item[1] or 0), str(item[0] or "")))
            ],
            "last_screens": [
                {"screen_key": str(key), "users": int(total or 0)}
                for key, total in sorted(last_screen_rows, key=lambda item: (-int(item[1] or 0), str(item[0] or "")))
            ],
        }

    def _get_flow_user_report_sync(self, user_id: int, days: int) -> dict:
        start_at = self._lookback_start(days)
        with self._session_factory() as session:
            user = session.query(User).filter(User.user_id == int(user_id)).first()
            events = (
                session.query(UserFlowEvent)
                .filter(
                    UserFlowEvent.user_id == int(user_id),
                    UserFlowEvent.created_at >= start_at,
                )
                .order_by(UserFlowEvent.created_at.desc())
                .limit(50)
                .all()
            )
        event_rows = []
        for event in events:
            meta = None
            if event.meta_json:
                try:
                    meta = json.loads(event.meta_json)
                except Exception:
                    meta = event.meta_json
            event_rows.append(
                {
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                    "event_type": event.event_type,
                    "screen_key": event.screen_key,
                    "action_key": event.action_key,
                    "source": event.source,
                    "meta": meta,
                }
            )
        return {
            "user_id": int(user_id),
            "days": max(int(days or 1), 1),
            "since_utc": start_at.isoformat(),
            "user_found": user is not None,
            "acquisition_source": None if user is None else user.acquisition_source,
            "acquisition_recorded_at": None
            if user is None or user.acquisition_recorded_at is None
            else user.acquisition_recorded_at.isoformat(),
            "last_screen_key": None if user is None else user.last_screen_key,
            "last_screen_at": None
            if user is None or user.last_screen_at is None
            else user.last_screen_at.isoformat(),
            "events": event_rows,
        }

    def _get_billing_report_sync(self, days: int) -> dict:
        start_at = self._lookback_start(days)
        providers = BILLING_REPORT_PROVIDERS
        duplicate_event_types = ("stars_payment_duplicate", "tbank_payment_duplicate")
        invalid_event_types = (
            "stars_payment_invalid",
            "stars_precheckout_rejected",
            "tbank_payment_invalid_amount",
            "tbank_payment_init_failed",
        )
        with self._session_factory() as session:
            events = (
                session.query(BillingEvent.event_type, func.count(BillingEvent.id))
                .filter(BillingEvent.provider.in_(providers), BillingEvent.created_at >= start_at)
                .group_by(BillingEvent.event_type)
                .all()
            )
            event_counts = {str(name): int(count or 0) for name, count in events}

            payments = (
                session.query(
                    Payment.provider,
                    Payment.status,
                    Payment.currency,
                    func.count(Payment.id),
                    func.coalesce(func.sum(Payment.price_final), 0),
                )
                .filter(Payment.provider.in_(providers), Payment.created_at >= start_at)
                .group_by(Payment.provider, Payment.status, Payment.currency)
                .all()
            )
            payment_counts: dict[str, int] = {}
            payment_amounts_stars: dict[str, int] = {}
            payment_breakdown: list[dict[str, object]] = []
            for provider, status, currency, count, amount in payments:
                provider_name = str(provider)
                status_name = str(status)
                currency_name = str(currency or "").strip() or "NA"
                count_value = int(count or 0)
                payment_counts[status_name] = int(payment_counts.get(status_name, 0)) + count_value
                if provider_name == "telegram_stars":
                    payment_amounts_stars[status_name] = int(
                        payment_amounts_stars.get(status_name, 0) + int(amount or 0)
                    )
                payment_breakdown.append(
                    {
                        "provider": provider_name,
                        "status": status_name,
                        "currency": currency_name,
                        "count": count_value,
                        "amount": str(amount),
                    }
                )
            payment_breakdown.sort(key=lambda row: (str(row["provider"]), str(row["status"]), str(row["currency"])))

            invalid_reasons = (
                session.query(BillingEvent.reason, func.count(BillingEvent.id))
                .filter(
                    BillingEvent.provider.in_(providers),
                    BillingEvent.created_at >= start_at,
                    BillingEvent.event_type.in_(invalid_event_types),
                    BillingEvent.reason.is_not(None),
                )
                .group_by(BillingEvent.reason)
                .all()
            )
            invalid_reason_counts = {
                str(reason): int(count or 0)
                for reason, count in invalid_reasons
                if str(reason or "").strip()
            }

            summary = {
                "paid": int(payment_counts.get("paid", 0)),
                "refunded": int(payment_counts.get("refunded", 0)),
                "duplicate": int(sum(int(event_counts.get(name, 0)) for name in duplicate_event_types)),
                "invalid": int(
                    sum(int(event_counts.get(name, 0)) for name in invalid_event_types)
                ),
            }
            total_events = int(sum(event_counts.values()))
            return {
                "days": max(int(days or 1), 1),
                "since_utc": start_at.isoformat(),
                "summary": summary,
                "event_counts": event_counts,
                "payment_counts": payment_counts,
                "payment_amounts_xtr": payment_amounts_stars,
                "payment_breakdown": payment_breakdown,
                "invalid_reason_counts": invalid_reason_counts,
                "events_total": total_events,
            }

    def _get_billing_suspicious_sync(
        self,
        days: int,
        refund_pending_minutes: int,
    ) -> dict:
        start_at = self._lookback_start(days)
        pending_cutoff = utcnow() - timedelta(minutes=max(int(refund_pending_minutes or 1), 1))
        issues: list[dict[str, object]] = []
        with self._session_factory() as session:
            pending = (
                session.query(Payment)
                .filter(
                    Payment.provider.in_(("telegram_stars", "tbank_sbp")),
                    Payment.status == PAYMENT_STATUS_REFUND_PENDING,
                    Payment.created_at >= start_at,
                    Payment.created_at < pending_cutoff,
                )
                .all()
            )
            for payment in pending:
                issues.append(
                    {
                        "kind": "refund_pending_too_long",
                        "payment_id": str(payment.id),
                        "user_id": payment.user_id,
                        "status": payment.status,
                        "minutes": int(refund_pending_minutes),
                    }
                )

            missing_charge = (
                session.query(Payment)
                .filter(
                    Payment.provider == "telegram_stars",
                    Payment.status == "paid",
                    Payment.created_at >= start_at,
                    (Payment.telegram_payment_charge_id.is_(None) | (Payment.telegram_payment_charge_id == "")),
                )
                .all()
            )
            for payment in missing_charge:
                issues.append(
                    {
                        "kind": "paid_missing_telegram_charge_id",
                        "payment_id": str(payment.id),
                        "user_id": payment.user_id,
                        "status": payment.status,
                    }
                )

            tbank_missing_provider_id = (
                session.query(Payment)
                .filter(
                    Payment.provider == "tbank_sbp",
                    Payment.status == "paid",
                    Payment.created_at >= start_at,
                    (Payment.provider_payment_id.is_(None) | (Payment.provider_payment_id == "")),
                )
                .all()
            )
            for payment in tbank_missing_provider_id:
                issues.append(
                    {
                        "kind": "paid_missing_tbank_payment_id",
                        "payment_id": str(payment.id),
                        "user_id": payment.user_id,
                        "status": payment.status,
                    }
                )

            invalid_credits = (
                session.query(Payment)
                .filter(
                    Payment.provider.in_(BILLING_REPORT_PROVIDERS),
                    Payment.status == "paid",
                    Payment.created_at >= start_at,
                    (Payment.credits_amount.is_(None) | (Payment.credits_amount <= 0)),
                )
                .all()
            )
            for payment in invalid_credits:
                issues.append(
                    {
                        "kind": "paid_invalid_credits_amount",
                        "payment_id": str(payment.id),
                        "user_id": payment.user_id,
                        "provider": payment.provider,
                        "credits_amount": int(payment.credits_amount or 0),
                    }
                )

            negative_users = (
                session.query(User)
                .filter(User.is_active.is_(False), User.usage_left.is_not(None), User.usage_left < 0)
                .all()
            )
            for user in negative_users:
                issues.append(
                    {
                        "kind": "negative_usage_left",
                        "user_id": user.user_id,
                        "usage_left": int(user.usage_left or 0),
                    }
                )

            users = (
                session.query(User)
                .filter(User.is_active.is_(False), User.usage_left.is_not(None))
                .all()
            )
            user_ids = [int(item.user_id) for item in users]
            per_user: dict[int, dict[str, int]] = {}
            if user_ids:
                # Use full ledger for mismatch checks to avoid false positives from N-day window bias.
                ledger = (
                    session.query(
                        BillingEvent.user_id,
                        BillingEvent.event_type,
                        func.coalesce(func.sum(BillingEvent.credits_amount), 0),
                    )
                    .filter(
                        BillingEvent.provider.in_(("telegram_stars", "tbank_sbp")),
                        BillingEvent.user_id.is_not(None),
                        BillingEvent.user_id.in_(user_ids),
                    )
                    .group_by(BillingEvent.user_id, BillingEvent.event_type)
                    .all()
                )
                for user_id, event_type, total in ledger:
                    uid = int(user_id)
                    bucket = per_user.setdefault(uid, {})
                    bucket[str(event_type)] = int(total or 0)

            for user in users:
                uid = int(user.user_id)
                events = per_user.get(uid, {})
                if not events:
                    continue
                # Legacy/manual grants can distort mismatch checks; skip these users.
                if int(events.get("admin_credit_grant", 0)) > 0:
                    continue
                inflow = int(events.get("stars_payment_paid", 0)) + int(events.get("tbank_payment_paid", 0))
                # Users without incoming credit events are usually legacy/manual cases.
                if inflow <= 0:
                    continue
                expected = (
                    inflow
                    - int(events.get("credits_spent", 0))
                    - int(events.get("stars_refund_applied", 0))
                    - int(events.get("tbank_payment_refunded", 0))
                    - int(events.get("tbank_refund_applied", 0))
                )
                actual = int(user.usage_left or 0)
                if expected != actual:
                    issues.append(
                        {
                            "kind": "usage_left_mismatch",
                            "user_id": uid,
                            "expected": expected,
                            "actual": actual,
                            "delta": actual - expected,
                        }
                    )

            return {
                "days": max(int(days or 1), 1),
                "since_utc": start_at.isoformat(),
                "issues_total": len(issues),
                "issues": issues,
            }

    def _get_billing_user_report_sync(self, user_id: int, days: int) -> dict:
        start_at = self._lookback_start(days)
        with self._session_factory() as session:
            events = (
                session.query(BillingEvent)
                .filter(
                    BillingEvent.provider.in_(BILLING_REPORT_PROVIDERS),
                    BillingEvent.user_id == int(user_id),
                    BillingEvent.created_at >= start_at,
                )
                .order_by(BillingEvent.created_at.desc())
                .limit(100)
                .all()
            )
            payments = (
                session.query(Payment)
                .filter(
                    Payment.provider.in_(BILLING_REPORT_PROVIDERS),
                    Payment.user_id == int(user_id),
                    Payment.created_at >= start_at,
                )
                .order_by(Payment.created_at.desc())
                .limit(30)
                .all()
            )
            user = session.query(User).filter(User.user_id == int(user_id)).first()
            event_counts: dict[str, int] = {}
            for event in events:
                key = str(event.event_type)
                event_counts[key] = int(event_counts.get(key, 0)) + 1

            return {
                "user_id": int(user_id),
                "days": max(int(days or 1), 1),
                "since_utc": start_at.isoformat(),
                "user_usage_left": None if user is None else user.usage_left,
                "user_is_active": None if user is None else bool(user.is_active),
                "acquisition_source": None if user is None else user.acquisition_source,
                "acquisition_recorded_at": None if user is None else user.acquisition_recorded_at,
                "event_counts": event_counts,
                "payments": [
                    {
                        "payment_id": str(item.id),
                        "provider": item.provider,
                        "status": item.status,
                        "amount": str(item.price_final),
                        "currency": item.currency,
                        "credits_amount": int(item.credits_amount or 0),
                        "provider_payment_id": item.provider_payment_id,
                        "telegram_payment_charge_id": item.telegram_payment_charge_id,
                        "created_at": item.created_at,
                        "paid_at": item.paid_at,
                        "refunded_at": item.refunded_at,
                    }
                    for item in payments
                ],
                "events": [
                    {
                        "event_type": item.event_type,
                        "reason": item.reason,
                        "credits_amount": item.credits_amount,
                        "stars_amount": item.stars_amount,
                        "provider_amount": (str(item.provider_amount) if item.provider_amount is not None else None),
                        "provider_payment_id": item.provider_payment_id,
                        "created_at": item.created_at,
                    }
                    for item in events
                ],
            }

    def _get_billing_reconciliation_sync(
        self,
        limit_users: int,
        min_abs_delta: int,
    ) -> dict:
        safe_limit = max(int(limit_users or 1), 1)
        threshold = max(int(min_abs_delta or 0), 0)

        with self._session_factory() as session:
            users = (
                session.query(User)
                .filter(User.is_active.is_(False), User.usage_left.is_not(None))
                .all()
            )
            user_ids = [int(item.user_id) for item in users]

            per_user: dict[int, dict[str, int]] = {}
            if user_ids:
                ledger = (
                    session.query(
                        BillingEvent.user_id,
                        BillingEvent.event_type,
                        func.coalesce(func.sum(BillingEvent.credits_amount), 0),
                    )
                    .filter(
                        BillingEvent.provider.in_(BILLING_REPORT_PROVIDERS),
                        BillingEvent.user_id.is_not(None),
                        BillingEvent.user_id.in_(user_ids),
                    )
                    .group_by(BillingEvent.user_id, BillingEvent.event_type)
                    .all()
                )
                for user_id, event_type, total in ledger:
                    uid = int(user_id)
                    bucket = per_user.setdefault(uid, {})
                    bucket[str(event_type)] = int(total or 0)

            mismatches: list[dict[str, object]] = []
            exact_count = 0
            expected_total = 0
            actual_total = 0

            for user in users:
                uid = int(user.user_id)
                events = per_user.get(uid, {})
                paid_total = int(events.get("stars_payment_paid", 0)) + int(
                    events.get("tbank_payment_paid", 0)
                )
                admin_grants = int(events.get("admin_credit_grant", 0))
                spent_total = int(events.get("credits_spent", 0))
                refund_total = (
                    int(events.get("stars_refund_applied", 0))
                    + int(events.get("tbank_payment_refunded", 0))
                    + int(events.get("tbank_refund_applied", 0))
                )
                expected = paid_total + admin_grants - spent_total - refund_total
                actual = int(user.usage_left or 0)
                delta = actual - expected

                expected_total += expected
                actual_total += actual

                if abs(delta) <= threshold:
                    exact_count += 1
                    continue

                mismatches.append(
                    {
                        "user_id": uid,
                        "actual": actual,
                        "expected": expected,
                        "delta": delta,
                        "paid_total": paid_total,
                        "admin_grants": admin_grants,
                        "spent_total": spent_total,
                        "refund_total": refund_total,
                    }
                )

            mismatches.sort(key=lambda item: abs(int(item["delta"])), reverse=True)
            return {
                "users_checked": len(users),
                "exact_count": exact_count,
                "mismatches_total": len(mismatches),
                "limit_users": safe_limit,
                "min_abs_delta": threshold,
                "expected_total": expected_total,
                "actual_total": actual_total,
                "total_delta": actual_total - expected_total,
                "mismatches": mismatches[:safe_limit],
            }

    def _register_webhook_event_sync(
        self,
        provider: str,
        event_type: str,
        idempotency_key: str,
        order_id: str | None,
        provider_payment_id: str | None,
        payload: dict[str, object] | None,
        max_attempts: int,
    ) -> dict:
        provider_name = self._normalize_billing_provider(provider)
        if provider_name is None:
            return self._unsupported_provider(provider)
        key = str(idempotency_key or "").strip()
        if not key:
            return {"status": "invalid_idempotency_key"}
        safe_attempts = max(int(max_attempts or 1), 1)
        payload_json = None
        if isinstance(payload, dict):
            try:
                payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            except Exception:
                payload_json = None
        now = utcnow()
        with self._session_factory() as session:
            event = (
                session.query(BillingWebhookEvent)
                .filter(
                    BillingWebhookEvent.provider == provider_name,
                    BillingWebhookEvent.idempotency_key == key,
                )
                .with_for_update()
                .first()
            )
            if event is None:
                event = BillingWebhookEvent(
                    provider=provider_name,
                    event_type=str(event_type or "payment_notification")[:64],
                    idempotency_key=key[:191],
                    status="received",
                    attempts=1,
                    order_id=(str(order_id or "").strip()[:128] or None),
                    provider_payment_id=(str(provider_payment_id or "").strip()[:128] or None),
                    payload_json=payload_json,
                    last_error=None,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                session.add(event)
                session.commit()
                session.refresh(event)
                return {
                    "status": "accepted",
                    "event_id": str(event.id),
                    "attempts": int(event.attempts or 1),
                    "should_process": True,
                }

            event.attempts = int(event.attempts or 0) + 1
            event.last_seen_at = now
            if provider_payment_id:
                event.provider_payment_id = str(provider_payment_id)[:128]
            if order_id:
                event.order_id = str(order_id)[:128]
            if payload_json:
                event.payload_json = payload_json

            if event.status in {"processed", "ignored"}:
                event.status = "duplicate"
                session.commit()
                return {
                    "status": "duplicate",
                    "event_id": str(event.id),
                    "attempts": int(event.attempts or 0),
                    "should_process": False,
                }

            if int(event.attempts or 0) > safe_attempts:
                event.status = "dead_letter"
                session.commit()
                return {
                    "status": "dead_letter",
                    "event_id": str(event.id),
                    "attempts": int(event.attempts or 0),
                    "should_process": False,
                }

            event.status = "received"
            session.commit()
            return {
                "status": "accepted_retry",
                "event_id": str(event.id),
                "attempts": int(event.attempts or 0),
                "should_process": True,
            }

    def _finalize_webhook_event_sync(
        self,
        event_id: str,
        status: str,
        error: str | None,
    ) -> dict:
        event_uuid = self._parse_uuid(event_id)
        if event_uuid is None:
            return {"status": "invalid_event_id"}
        normalized_status = str(status or "").strip().lower() or "processed"
        allowed = {"processed", "ignored", "failed", "dead_letter", "duplicate"}
        if normalized_status not in allowed:
            normalized_status = "processed"
        now = utcnow()
        with self._session_factory() as session:
            event = (
                session.query(BillingWebhookEvent)
                .filter(BillingWebhookEvent.id == event_uuid)
                .with_for_update()
                .first()
            )
            if event is None:
                return {"status": "not_found"}
            event.status = normalized_status
            event.last_error = str(error or "")[:4000] or None
            event.updated_at = now
            if normalized_status in {"processed", "ignored", "duplicate"}:
                event.processed_at = now
            session.commit()
            return {"status": "ok", "event_status": event.status}

    def _get_webhook_event_sync(self, event_id: str) -> dict:
        event_uuid = self._parse_uuid(event_id)
        if event_uuid is None:
            return {"status": "invalid_event_id"}
        with self._session_factory() as session:
            event = (
                session.query(BillingWebhookEvent)
                .filter(BillingWebhookEvent.id == event_uuid)
                .first()
            )
            if event is None:
                return {"status": "not_found"}
            payload = None
            if event.payload_json:
                try:
                    parsed = json.loads(event.payload_json)
                    if isinstance(parsed, dict):
                        payload = parsed
                except Exception:
                    payload = None
            return {
                "status": "ok",
                "event_id": str(event.id),
                "provider": event.provider,
                "event_type": event.event_type,
                "idempotency_key": event.idempotency_key,
                "event_status": event.status,
                "attempts": int(event.attempts or 0),
                "order_id": event.order_id,
                "provider_payment_id": event.provider_payment_id,
                "last_error": event.last_error,
                "payload": payload,
                "processed_at": event.processed_at,
                "last_seen_at": event.last_seen_at,
            }

    def _list_webhook_dead_letters_sync(self, provider: str, limit: int) -> dict:
        provider_name = self._normalize_billing_provider(provider)
        if provider_name is None:
            return self._unsupported_provider(provider)
        safe_limit = max(int(limit or 1), 1)
        with self._session_factory() as session:
            events = (
                session.query(BillingWebhookEvent)
                .filter(
                    BillingWebhookEvent.provider == provider_name,
                    BillingWebhookEvent.status == "dead_letter",
                )
                .order_by(BillingWebhookEvent.last_seen_at.desc())
                .limit(safe_limit)
                .all()
            )
            return {
                "status": "ok",
                "provider": provider_name,
                "items": [
                    {
                        "event_id": str(item.id),
                        "event_type": item.event_type,
                        "attempts": int(item.attempts or 0),
                        "order_id": item.order_id,
                        "provider_payment_id": item.provider_payment_id,
                        "last_error": item.last_error,
                        "last_seen_at": item.last_seen_at,
                    }
                    for item in events
                ],
            }

    def _lookup_stars_payment_sync(self, query: str) -> dict:
        needle = str(query or "").strip()
        if not needle:
            return {"status": "invalid_query"}

        with self._session_factory() as session:
            payment = None
            payment_uuid = self._parse_payment_uuid(needle)
            if payment_uuid is not None:
                payment = (
                    session.query(Payment)
                    .filter(
                        Payment.id == payment_uuid,
                        Payment.provider == "telegram_stars",
                    )
                    .first()
                )
            if payment is None:
                payment = (
                    session.query(Payment)
                    .filter(
                        Payment.provider == "telegram_stars",
                        Payment.provider_payment_id == needle,
                    )
                    .order_by(Payment.created_at.desc())
                    .first()
                )
            if payment is None:
                payment = (
                    session.query(Payment)
                    .filter(
                        Payment.provider == "telegram_stars",
                        Payment.telegram_payment_charge_id == needle,
                    )
                    .order_by(Payment.created_at.desc())
                    .first()
                )
            if payment is None:
                return {"status": "not_found"}

            user = session.query(User).filter(User.user_id == payment.user_id).first()
            remaining = None
            if user and not user.is_active and user.usage_left is not None:
                remaining = max(int(user.usage_left or 0), 0)

            return {
                "status": "ok",
                "payment_id": str(payment.id),
                "user_id": payment.user_id,
                "payment_status": payment.status,
                "provider_payment_id": payment.provider_payment_id,
                "telegram_payment_charge_id": payment.telegram_payment_charge_id,
                "credits_amount": int(payment.credits_amount or 0),
                "stars_amount": int(payment.price_final or 0),
                "currency": payment.currency,
                "paid_at": payment.paid_at,
                "refunded_at": payment.refunded_at,
                "remaining_requests": remaining,
            }

    def _lookup_tbank_payment_sync(self, query: str) -> dict:
        needle = str(query or "").strip()
        if not needle:
            return {"status": "invalid_query"}

        with self._session_factory() as session:
            payment = None
            payment_uuid = self._parse_payment_uuid(needle)
            if payment_uuid is not None:
                payment = (
                    session.query(Payment)
                    .filter(
                        Payment.id == payment_uuid,
                        Payment.provider == "tbank_sbp",
                        Payment.user_id.is_not(None),
                    )
                    .first()
                )
            if payment is None:
                payment = (
                    session.query(Payment)
                    .filter(
                        Payment.provider == "tbank_sbp",
                        Payment.user_id.is_not(None),
                        Payment.provider_payment_id == needle,
                    )
                    .order_by(Payment.created_at.desc())
                    .first()
                )
            if payment is None:
                return {"status": "not_found"}

            user = session.query(User).filter(User.user_id == payment.user_id).first()
            remaining = None
            if user and not user.is_active and user.usage_left is not None:
                remaining = max(int(user.usage_left or 0), 0)

            return {
                "status": "ok",
                "payment_id": str(payment.id),
                "user_id": payment.user_id,
                "payment_status": payment.status,
                "provider_payment_id": payment.provider_payment_id,
                "credits_amount": int(payment.credits_amount or 0),
                "amount_rub": str(payment.price_final),
                "currency": payment.currency,
                "paid_at": payment.paid_at,
                "refunded_at": payment.refunded_at,
                "remaining_requests": remaining,
            }

    def _get_tbank_payment_link_message_sync(self, payment_id: str) -> dict:
        payment_uuid = self._parse_payment_uuid(str(payment_id or "").strip())
        if payment_uuid is None:
            return {"status": "invalid_payment_id"}
        with self._session_factory() as session:
            event = (
                session.query(BillingEvent)
                .filter(
                    BillingEvent.provider == "tbank_sbp",
                    BillingEvent.event_type == "tbank_payment_link_sent",
                    BillingEvent.payment_id == payment_uuid,
                )
                .order_by(BillingEvent.created_at.desc())
                .first()
            )
            if event is None:
                return {"status": "not_found"}
            meta = {}
            if event.meta_json:
                try:
                    parsed = json.loads(event.meta_json)
                    if isinstance(parsed, dict):
                        meta = parsed
                except Exception:
                    meta = {}
            message_id_raw = meta.get("message_id")
            chat_id_raw = meta.get("chat_id")
            try:
                message_id = int(message_id_raw)
            except Exception:
                message_id = None
            try:
                chat_id = int(chat_id_raw)
            except Exception:
                chat_id = int(event.user_id) if event.user_id is not None else None
            if message_id is None or chat_id is None:
                return {"status": "not_found"}
            return {
                "status": "ok",
                "chat_id": chat_id,
                "message_id": message_id,
            }

    def _start_stars_refund_sync(self, payment_id: str) -> dict:
        payment_uuid = self._parse_payment_uuid(payment_id)
        if payment_uuid is None:
            return {"status": "invalid_payment_id"}

        with self._session_factory() as session:
            payment = (
                session.query(Payment)
                .filter(
                    Payment.id == payment_uuid,
                    Payment.user_id.is_not(None),
                )
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if payment.provider != "telegram_stars":
                return {"status": "unsupported_provider"}
            if payment.status == PAYMENT_STATUS_REFUNDED:
                self._record_billing_event_sync(
                    provider="telegram_stars",
                    event_type="stars_refund_duplicate",
                    user_id=payment.user_id,
                    payment_id=str(payment.id),
                    provider_payment_id=payment.provider_payment_id,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    currency=payment.currency,
                    stars_amount=int(payment.price_final or 0),
                    credits_amount=int(payment.credits_amount or 0),
                    reason="already_refunded",
                    meta=None,
                )
                return {"status": "duplicate_refund"}
            if payment.status == PAYMENT_STATUS_REFUND_PENDING:
                self._record_billing_event_sync(
                    provider="telegram_stars",
                    event_type="stars_refund_in_progress",
                    user_id=payment.user_id,
                    payment_id=str(payment.id),
                    provider_payment_id=payment.provider_payment_id,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    currency=payment.currency,
                    stars_amount=int(payment.price_final or 0),
                    credits_amount=int(payment.credits_amount or 0),
                    reason="already_pending",
                    meta=None,
                )
                return {"status": "in_progress"}
            if payment.status != "paid":
                return {"status": "not_paid", "payment_status": payment.status}

            telegram_charge_id = str(payment.telegram_payment_charge_id or "").strip()
            if not telegram_charge_id:
                return {"status": "missing_telegram_charge_id"}

            credits_amount = max(int(payment.credits_amount or 0), 0)
            if credits_amount <= 0:
                return {"status": "invalid_credits_amount"}

            user = (
                session.query(User)
                .filter(User.user_id == payment.user_id)
                .with_for_update()
                .first()
            )
            if user is None:
                return {"status": "user_not_found"}
            if user.is_active:
                return {"status": "manual_unlimited_not_supported"}
            if user.usage_left is None:
                return {"status": "unlimited_credits_not_supported"}

            remaining_before = max(int(user.usage_left or 0), 0)
            if remaining_before < credits_amount:
                self._record_billing_event_sync(
                    provider="telegram_stars",
                    event_type="stars_refund_rejected",
                    user_id=payment.user_id,
                    payment_id=str(payment.id),
                    provider_payment_id=payment.provider_payment_id,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    currency=payment.currency,
                    stars_amount=int(payment.price_final or 0),
                    credits_amount=credits_amount,
                    reason="insufficient_unused_credits",
                    meta={"remaining_requests": remaining_before},
                )
                return {
                    "status": "insufficient_unused_credits",
                    "remaining_requests": remaining_before,
                    "required_credits": credits_amount,
                }

            remaining_after_hold = remaining_before - credits_amount
            user.usage_left = remaining_after_hold
            user.credits_status = (
                CREDITS_STATUS_ACTIVE if remaining_after_hold > 0 else CREDITS_STATUS_EXHAUSTED
            )
            payment.status = PAYMENT_STATUS_REFUND_PENDING
            session.commit()
            self._record_billing_event_sync(
                provider="telegram_stars",
                event_type="stars_refund_requested",
                user_id=payment.user_id,
                payment_id=str(payment.id),
                provider_payment_id=payment.provider_payment_id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
                currency=payment.currency,
                stars_amount=int(payment.price_final or 0),
                credits_amount=credits_amount,
                reason=None,
                meta={
                    "remaining_before": remaining_before,
                    "remaining_after_hold": remaining_after_hold,
                },
            )
            logger.info(
                "stars_refund_requested payment_id=%s user_id=%s credits=%s remaining_before=%s remaining_after_hold=%s",
                str(payment.id),
                payment.user_id,
                credits_amount,
                remaining_before,
                remaining_after_hold,
            )
            return {
                "status": "ready",
                "payment_id": str(payment.id),
                "user_id": payment.user_id,
                "telegram_payment_charge_id": telegram_charge_id,
                "credits_amount": credits_amount,
                "remaining_requests": remaining_after_hold,
            }

    def _start_tbank_refund_sync(self, payment_id: str) -> dict:
        payment_uuid = self._parse_payment_uuid(payment_id)
        if payment_uuid is None:
            return {"status": "invalid_payment_id"}

        with self._session_factory() as session:
            payment = (
                session.query(Payment)
                .filter(
                    Payment.id == payment_uuid,
                    Payment.user_id.is_not(None),
                )
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if payment.provider != "tbank_sbp":
                return {"status": "unsupported_provider"}
            if payment.status == PAYMENT_STATUS_REFUNDED:
                self._record_billing_event_sync(
                    provider="tbank_sbp",
                    event_type="tbank_refund_duplicate",
                    user_id=payment.user_id,
                    payment_id=str(payment.id),
                    provider_payment_id=payment.provider_payment_id,
                    telegram_payment_charge_id=None,
                    currency=payment.currency,
                    stars_amount=int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1"))),
                    credits_amount=int(payment.credits_amount or 0),
                    reason="already_refunded",
                    meta=None,
                )
                return {"status": "duplicate_refund"}
            if payment.status == PAYMENT_STATUS_REFUND_PENDING:
                return {"status": "in_progress"}

            provider_payment_id = str(payment.provider_payment_id or "").strip()
            if not provider_payment_id:
                return {"status": "missing_provider_payment_id"}

            credits_amount = max(int(payment.credits_amount or 0), 0)
            remaining_after_hold: int | None = None
            local_mode = "cancel"

            if payment.status == "paid":
                local_mode = "refund"
                user = (
                    session.query(User)
                    .filter(User.user_id == payment.user_id)
                    .with_for_update()
                    .first()
                )
                if user is None:
                    return {"status": "user_not_found"}
                if user.is_active:
                    return {"status": "manual_unlimited_not_supported"}
                if user.usage_left is None:
                    return {"status": "unlimited_credits_not_supported"}

                remaining_before = max(int(user.usage_left or 0), 0)
                if remaining_before < credits_amount:
                    self._record_billing_event_sync(
                        provider="tbank_sbp",
                        event_type="tbank_refund_rejected",
                        user_id=payment.user_id,
                        payment_id=str(payment.id),
                        provider_payment_id=payment.provider_payment_id,
                        telegram_payment_charge_id=None,
                        currency=payment.currency,
                        stars_amount=int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1"))),
                        credits_amount=credits_amount,
                        reason="insufficient_unused_credits",
                        meta={"remaining_requests": remaining_before},
                    )
                    return {
                        "status": "insufficient_unused_credits",
                        "remaining_requests": remaining_before,
                        "required_credits": credits_amount,
                    }
                remaining_after_hold = remaining_before - credits_amount
                user.usage_left = remaining_after_hold
                user.credits_status = (
                    CREDITS_STATUS_ACTIVE if remaining_after_hold > 0 else CREDITS_STATUS_EXHAUSTED
                )
                payment.status = PAYMENT_STATUS_REFUND_PENDING

            elif payment.status not in {"pending", "authorized", "confirmed"}:
                return {"status": "not_refundable_status", "payment_status": payment.status}

            session.commit()
            self._record_billing_event_sync(
                provider="tbank_sbp",
                event_type="tbank_refund_requested",
                user_id=payment.user_id,
                payment_id=str(payment.id),
                provider_payment_id=payment.provider_payment_id,
                telegram_payment_charge_id=None,
                currency=payment.currency,
                stars_amount=int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1"))),
                credits_amount=credits_amount,
                reason=local_mode,
                meta={"remaining_after_hold": remaining_after_hold},
            )
            return {
                "status": "ready",
                "payment_id": str(payment.id),
                "provider_payment_id": provider_payment_id,
                "user_id": payment.user_id,
                "credits_amount": credits_amount,
                "amount_kopecks": int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1"))),
                "remaining_requests": remaining_after_hold,
                "local_mode": local_mode,
            }

    def _finalize_stars_refund_sync(
        self,
        payment_id: str,
        success: bool,
        reason: str | None,
        telegram_error: str | None,
    ) -> dict:
        payment_uuid = self._parse_payment_uuid(payment_id)
        if payment_uuid is None:
            return {"status": "invalid_payment_id"}

        with self._session_factory() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == payment_uuid)
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if payment.provider != "telegram_stars":
                return {"status": "unsupported_provider"}
            if payment.status == PAYMENT_STATUS_REFUNDED:
                self._record_billing_event_sync(
                    provider="telegram_stars",
                    event_type="stars_refund_duplicate",
                    user_id=payment.user_id,
                    payment_id=str(payment.id),
                    provider_payment_id=payment.provider_payment_id,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    currency=payment.currency,
                    stars_amount=int(payment.price_final or 0),
                    credits_amount=int(payment.credits_amount or 0),
                    reason="already_refunded",
                    meta=None,
                )
                return {"status": "duplicate_refund"}

            user = (
                session.query(User)
                .filter(User.user_id == payment.user_id)
                .with_for_update()
                .first()
            )
            if user is None:
                if payment.status == PAYMENT_STATUS_REFUND_PENDING:
                    payment.status = "paid"
                    session.commit()
                return {"status": "user_not_found"}

            if not success:
                if payment.status == PAYMENT_STATUS_REFUND_PENDING:
                    credits_amount = max(int(payment.credits_amount or 0), 0)
                    user.usage_left = max(int(user.usage_left or 0), 0) + credits_amount
                    user.credits_status = (
                        CREDITS_STATUS_ACTIVE if int(user.usage_left or 0) > 0 else CREDITS_STATUS_EXHAUSTED
                    )
                    payment.status = "paid"
                    session.commit()
                self._record_billing_event_sync(
                    provider="telegram_stars",
                    event_type="stars_refund_error",
                    user_id=payment.user_id,
                    payment_id=str(payment.id),
                    provider_payment_id=payment.provider_payment_id,
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    currency=payment.currency,
                    stars_amount=int(payment.price_final or 0),
                    credits_amount=int(payment.credits_amount or 0),
                    reason="telegram_api_error",
                    meta={"error": str(telegram_error or "unknown")},
                )
                logger.warning(
                    "stars_refund_error payment_id=%s user_id=%s error=%s",
                    str(payment.id),
                    payment.user_id,
                    str(telegram_error or "unknown"),
                )
                return {"status": "telegram_error", "error": telegram_error}

            if payment.status not in {PAYMENT_STATUS_REFUND_PENDING, "paid"}:
                return {"status": "invalid_state", "payment_status": payment.status}
            if user.is_active or user.usage_left is None:
                payment.status = "paid"
                session.commit()
                return {"status": "unlimited_credits_not_supported"}

            credits_amount = max(int(payment.credits_amount or 0), 0)
            remaining_before = max(int(user.usage_left or 0), 0)
            remaining_after = remaining_before
            if payment.status == "paid":
                if remaining_before < credits_amount:
                    payment.status = "paid"
                    session.commit()
                    self._record_billing_event_sync(
                        provider="telegram_stars",
                        event_type="stars_refund_rejected",
                        user_id=payment.user_id,
                        payment_id=str(payment.id),
                        provider_payment_id=payment.provider_payment_id,
                        telegram_payment_charge_id=payment.telegram_payment_charge_id,
                        currency=payment.currency,
                        stars_amount=int(payment.price_final or 0),
                        credits_amount=credits_amount,
                        reason="insufficient_unused_credits",
                        meta={"remaining_requests": remaining_before},
                    )
                    logger.warning(
                        "stars_refund_rejected payment_id=%s user_id=%s reason=insufficient_unused_credits remaining=%s required=%s",
                        str(payment.id),
                        payment.user_id,
                        remaining_before,
                        credits_amount,
                    )
                    return {
                        "status": "insufficient_unused_credits",
                        "remaining_requests": remaining_before,
                        "required_credits": credits_amount,
                    }
                remaining_after = remaining_before - credits_amount
                user.usage_left = remaining_after
                user.credits_status = (
                    CREDITS_STATUS_ACTIVE if remaining_after > 0 else CREDITS_STATUS_EXHAUSTED
                )
            payment.status = PAYMENT_STATUS_REFUNDED
            payment.refunded_at = utcnow()
            payment.refund_reason = str(reason or "").strip() or None
            session.commit()
            self._record_billing_event_sync(
                provider="telegram_stars",
                event_type="stars_refund_applied",
                user_id=payment.user_id,
                payment_id=str(payment.id),
                provider_payment_id=payment.provider_payment_id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
                currency=payment.currency,
                stars_amount=int(payment.price_final or 0),
                credits_amount=credits_amount,
                reason=payment.refund_reason,
                meta={
                    "remaining_before": remaining_before,
                    "remaining_after": remaining_after,
                },
            )
            logger.info(
                "stars_refund_applied payment_id=%s user_id=%s credits=%s remaining_before=%s remaining_after=%s",
                str(payment.id),
                payment.user_id,
                credits_amount,
                remaining_before,
                remaining_after,
            )
            return {
                "status": "applied",
                "payment_id": str(payment.id),
                "user_id": payment.user_id,
                "remaining_requests": remaining_after,
            }

    def _finalize_tbank_refund_sync(
        self,
        payment_id: str,
        success: bool,
        reason: str | None,
        tbank_error: str | None,
        tbank_status: str | None,
    ) -> dict:
        payment_uuid = self._parse_payment_uuid(payment_id)
        if payment_uuid is None:
            return {"status": "invalid_payment_id"}

        with self._session_factory() as session:
            payment = (
                session.query(Payment)
                .filter(Payment.id == payment_uuid)
                .with_for_update()
                .first()
            )
            if payment is None:
                return {"status": "not_found"}
            if payment.provider != "tbank_sbp":
                return {"status": "unsupported_provider"}

            user = (
                session.query(User)
                .filter(User.user_id == payment.user_id)
                .with_for_update()
                .first()
            )

            credits_amount = max(int(payment.credits_amount or 0), 0)
            amount_kopecks = int((Decimal(payment.price_final or 0) * Decimal("100")).quantize(Decimal("1")))
            is_paid_refund_flow = payment.status == PAYMENT_STATUS_REFUND_PENDING

            if not success:
                if is_paid_refund_flow and user is not None and not user.is_active:
                    base = max(int(user.usage_left or 0), 0)
                    user.usage_left = base + credits_amount
                    user.credits_status = (
                        CREDITS_STATUS_ACTIVE if int(user.usage_left or 0) > 0 else CREDITS_STATUS_EXHAUSTED
                    )
                    payment.status = "paid"
                session.commit()
                self._record_billing_event_sync(
                    provider="tbank_sbp",
                    event_type="tbank_refund_error",
                    user_id=payment.user_id,
                    payment_id=str(payment.id),
                    provider_payment_id=payment.provider_payment_id,
                    telegram_payment_charge_id=None,
                    currency=payment.currency,
                    stars_amount=amount_kopecks,
                    credits_amount=credits_amount,
                    reason="tbank_api_error",
                    meta={
                        "error": str(tbank_error or "unknown"),
                        "status": str(tbank_status or "").strip() or None,
                    },
                )
                return {"status": "tbank_error", "error": tbank_error}

            if payment.status == PAYMENT_STATUS_REFUNDED:
                return {"status": "duplicate_refund"}

            if is_paid_refund_flow:
                remaining_after = None
                if user is not None and not user.is_active and user.usage_left is not None:
                    remaining_after = max(int(user.usage_left or 0), 0)
                payment.status = PAYMENT_STATUS_REFUNDED
                payment.refunded_at = utcnow()
                payment.refund_reason = str(reason or "").strip() or "admin_tbank_refund"
                session.commit()
                self._record_billing_event_sync(
                    provider="tbank_sbp",
                    event_type="tbank_refund_applied",
                    user_id=payment.user_id,
                    payment_id=str(payment.id),
                    provider_payment_id=payment.provider_payment_id,
                    telegram_payment_charge_id=None,
                    currency=payment.currency,
                    stars_amount=amount_kopecks,
                    credits_amount=credits_amount,
                    reason=payment.refund_reason,
                    meta={
                        "status": str(tbank_status or "").strip() or None,
                        "mode": "refund",
                    },
                )
                return {
                    "status": "applied",
                    "payment_id": str(payment.id),
                    "user_id": payment.user_id,
                    "remaining_requests": remaining_after,
                    "mode": "refund",
                }

            payment.status = "canceled"
            payment.refund_reason = str(reason or "").strip() or "admin_tbank_cancel"
            session.commit()
            self._record_billing_event_sync(
                provider="tbank_sbp",
                event_type="tbank_cancel_applied",
                user_id=payment.user_id,
                payment_id=str(payment.id),
                provider_payment_id=payment.provider_payment_id,
                telegram_payment_charge_id=None,
                currency=payment.currency,
                stars_amount=amount_kopecks,
                credits_amount=credits_amount,
                reason=payment.refund_reason,
                meta={
                    "status": str(tbank_status or "").strip() or None,
                    "mode": "cancel",
                },
            )
            return {
                "status": "applied",
                "payment_id": str(payment.id),
                "user_id": payment.user_id,
                "remaining_requests": None,
                "mode": "cancel",
            }

    @staticmethod
    def _parse_payment_uuid(value: str) -> UUID | None:
        return WhitelistService._parse_uuid(value)

    def _list_whitelisted_sync(self) -> list[dict]:
        users: list[dict] = []
        with self._session_factory() as session:
            all_users = session.query(User).all()
            for user in all_users:
                source = None
                remaining: int | None
                if user.is_active:
                    source = "manual"
                    remaining = None
                elif user.usage_left is None and user.credits_status == CREDITS_STATUS_ACTIVE:
                    source = "credits"
                    remaining = None
                else:
                    current_left = max(int(user.usage_left or 0), 0)
                    if current_left > 0:
                        source = "credits"
                        remaining = current_left
                    else:
                        continue
                users.append(
                    {
                        "user_id": user.user_id,
                        "username": user.username,
                        "expires_at": None,
                        "remaining_requests": remaining,
                        "source": source,
                    }
                )
        return users
