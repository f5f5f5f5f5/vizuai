from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models.base import Base
from models.billing_event_model import BillingEvent
from models.billing_webhook_event_model import BillingWebhookEvent
from models.payment_model import Payment
from models.promocode_model import Promocode
from models.promocode_usage_model import PromocodeUsage
from models.user_model import User
from services.whitelist_service import WhitelistService
from utils.time import utcnow


@pytest.fixture
def session_factory(tmp_path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    @contextmanager
    def _session():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    return _session


@pytest.fixture
def whitelist_service(session_factory):
    service = WhitelistService()
    service._session_factory = session_factory
    return service


@pytest.mark.asyncio
async def test_manual_whitelist_overrides(session_factory, whitelist_service):
    user_id = 101
    await whitelist_service.ensure_user(user_id, username="tester")
    with session_factory() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        user.is_active = True
        session.commit()

    status = await whitelist_service.get_whitelist_status(user_id)
    assert status["whitelisted"] is True
    assert status["reason"] == "manual"


@pytest.mark.asyncio
async def test_credits_quota_exhausted(whitelist_service):
    user_id = 102
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.add_user_to_whitelist(user_id, days=1, requests=2)

    status = await whitelist_service.get_whitelist_status(user_id)
    assert status["whitelisted"] is True
    assert status["remaining_requests"] == 2

    first = await whitelist_service.reserve_units(user_id, 1)
    assert first["allowed"] is True
    assert first["remaining_requests"] == 1

    status = await whitelist_service.get_whitelist_status(user_id)
    assert status["remaining_requests"] == 1

    second = await whitelist_service.reserve_units(user_id, 1)
    assert second["allowed"] is True
    assert second["remaining_requests"] == 0

    status = await whitelist_service.get_whitelist_status(user_id)
    assert status["whitelisted"] is False
    assert status["reason"] in {"exhausted", "insufficient_credits"}


@pytest.mark.asyncio
async def test_insufficient_credits_status(session_factory, whitelist_service):
    user_id = 103
    await whitelist_service.ensure_user(user_id)
    status = await whitelist_service.get_whitelist_status(user_id)
    assert status["whitelisted"] is False
    assert status["reason"] == "insufficient_credits"


@pytest.mark.asyncio
async def test_reset_quota(whitelist_service):
    user_id = 104
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.add_user_to_whitelist(user_id, days=1, requests=3)

    await whitelist_service.reserve_units(user_id, 2)

    user = await whitelist_service.reset_quota(user_id)
    assert user is not None
    assert user.usage_left == 0
    assert user.credits_status == "no_credits"
    assert user.is_active is False


@pytest.mark.asyncio
async def test_add_credits_disables_manual_unlimited(session_factory, whitelist_service):
    user_id = 1041
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        user.is_active = True
        session.commit()

    await whitelist_service.add_user_to_whitelist(user_id, days=None, requests=11)
    status = await whitelist_service.get_whitelist_status(user_id)
    assert status["whitelisted"] is True
    assert status["remaining_requests"] == 11
    assert status["reason"] == "ok"

    with session_factory() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        assert user is not None
        assert user.is_active is False
        assert user.usage_left == 11


@pytest.mark.asyncio
async def test_list_whitelisted_users(session_factory, whitelist_service):
    manual_user = 201
    sub_user = 202

    await whitelist_service.ensure_user(manual_user)
    await whitelist_service.ensure_user(sub_user)
    await whitelist_service.add_user_to_whitelist(sub_user, days=1, requests=5)

    with session_factory() as session:
        user = session.query(User).filter(User.user_id == manual_user).first()
        user.is_active = True
        session.commit()

    users = await whitelist_service.list_whitelisted_users()
    user_ids = {item["user_id"] for item in users}
    assert manual_user in user_ids
    assert sub_user in user_ids


@pytest.mark.asyncio
async def test_apply_stars_payment_adds_credits_and_is_idempotent(session_factory, whitelist_service):
    user_id = 301
    await whitelist_service.ensure_user(user_id)

    first = await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:test-charge-1",
        telegram_payment_charge_id="telegram-charge-1",
    )
    assert first["status"] == "applied"
    assert first["remaining_requests"] == 10

    duplicate = await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:test-charge-1",
        telegram_payment_charge_id="telegram-charge-1",
    )
    assert duplicate["status"] == "duplicate"

    with session_factory() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        assert user is not None
        assert user.usage_left == 10
        assert user.credits_status == "active"
        payments = (
            session.query(Payment)
            .filter(Payment.user_id == user_id, Payment.provider == "telegram_stars")
            .all()
        )
        assert len(payments) == 1
        assert payments[0].telegram_payment_charge_id == "telegram-charge-1"
        assert payments[0].credits_amount == 10


@pytest.mark.asyncio
async def test_stars_checkout_intent_apply_flow(session_factory, whitelist_service):
    user_id = 3051
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_stars_payment_intent(
        user_id=user_id,
        credits=5,
        stars_amount=109,
    )
    assert intent["status"] == "ok"
    payment_id = str(intent["payment_id"])

    pre = await whitelist_service.validate_stars_checkout_intent(
        payment_id=payment_id,
        user_id=user_id,
        credits=5,
        stars_amount=109,
    )
    assert pre["status"] == "ok"

    mark = await whitelist_service.mark_stars_payment_invoice_sent(
        payment_id=payment_id,
        invoice_meta={"source": "test"},
    )
    assert mark["status"] == "ok"

    applied = await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=5,
        stars_amount=109,
        provider_payment_id="tg:checkout-intent-1",
        telegram_payment_charge_id="tg-charge-checkout-intent-1",
        checkout_payment_id=payment_id,
    )
    assert applied["status"] == "applied"
    assert applied["remaining_requests"] == 5

    duplicate = await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=5,
        stars_amount=109,
        provider_payment_id="tg:checkout-intent-1",
        telegram_payment_charge_id="tg-charge-checkout-intent-1",
        checkout_payment_id=payment_id,
    )
    assert duplicate["status"] == "duplicate"

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        assert payment is not None
        assert payment.status == "paid"
        assert payment.provider_payment_id == "tg:checkout-intent-1"
        assert payment.telegram_payment_charge_id == "tg-charge-checkout-intent-1"
        user = session.query(User).filter(User.user_id == user_id).first()
        assert user is not None
        assert user.usage_left == 5


@pytest.mark.asyncio
async def test_tbank_payment_apply_is_idempotent(session_factory, whitelist_service):
    user_id = 306
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=20,
        amount_rub=Decimal("519"),
    )
    assert intent["status"] == "ok"
    payment_id = str(intent["payment_id"])

    initialized = await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank-payment-1",
        init_meta={"status": "NEW"},
    )
    assert initialized["status"] == "ok"

    applied = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=51900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED", "AUTHORIZED"},
    )
    assert applied["status"] == "applied"
    assert applied["remaining_requests"] == 20
    assert applied["credits"] == 20

    duplicate = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=51900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED", "AUTHORIZED"},
    )
    assert duplicate["status"] == "duplicate"

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        user = session.query(User).filter(User.user_id == user_id).first()
        assert payment is not None
        assert payment.provider == "tbank_sbp"
        assert payment.status == "paid"
        assert payment.credits_amount == 20
        assert payment.provider_payment_id == "tbank-payment-1"
        assert user is not None
        assert user.usage_left == 20
        paid_events = (
            session.query(BillingEvent)
            .filter(
                BillingEvent.provider == "tbank_sbp",
                BillingEvent.event_type == "tbank_payment_paid",
                BillingEvent.payment_id == UUID(payment_id),
            )
            .all()
        )
        assert len(paid_events) == 1


@pytest.mark.asyncio
async def test_tbank_payment_invalid_amount_is_rejected(session_factory, whitelist_service):
    user_id = 307
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=1,
        amount_rub=Decimal("29"),
    )
    payment_id = str(intent["payment_id"])

    result = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-2",
        status="CONFIRMED",
        success=True,
        amount_kopecks=2800,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-2", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )
    assert result["status"] == "invalid_amount"
    assert result["expected_kopecks"] == 2900
    assert result["actual_kopecks"] == 2800

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        user = session.query(User).filter(User.user_id == user_id).first()
        assert payment is not None
        assert payment.status == "pending"
        assert user is not None
        assert user.usage_left == 0


@pytest.mark.asyncio
async def test_tbank_payment_non_success_status_is_ignored(session_factory, whitelist_service):
    user_id = 308
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=5,
        amount_rub=Decimal("139"),
    )
    payment_id = str(intent["payment_id"])
    result = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-3",
        status="REJECTED",
        success=False,
        amount_kopecks=13900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-3", "Status": "REJECTED"},
        accept_statuses={"CONFIRMED", "AUTHORIZED"},
    )
    assert result["status"] == "ignored"
    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        assert payment is not None
        assert payment.status == "rejected"


@pytest.mark.asyncio
async def test_tbank_promocode_reserve_intent_and_apply_redeems_usage(session_factory, whitelist_service):
    user_id = 3081
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        promo = Promocode(
            code_string="TBANK20",
            discount_type="fixed",
            discount_amount=Decimal("20"),
            code_amount=5,
            code_left=5,
            max_uses_per_user=5,
            is_active=True,
        )
        session.add(promo)
        session.commit()
        promo_id = promo.id

    reserved = await whitelist_service.reserve_promocode(
        user_id=user_id,
        code="tbank20",
        credits=5,
        stars_original=139,
        ttl_seconds=3600,
        provider="tbank_sbp",
        currency="RUB",
    )
    assert reserved["status"] == "ok"
    assert reserved["stars_final"] == 119

    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=5,
        amount_rub=Decimal("119"),
        promo_reservation_id=reserved["reservation_id"],
        promo_code_id=reserved["code_id"],
        amount_original_rub=Decimal("139"),
        discount_rub=Decimal("20"),
    )
    assert intent["status"] == "ok"
    payment_id = str(intent["payment_id"])

    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank-payment-promo-1",
        init_meta={"status": "NEW"},
    )
    applied = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-promo-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=11900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-promo-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )
    assert applied["status"] == "applied"
    assert applied["remaining_requests"] == 5

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        assert payment is not None
        assert payment.promocode_id == promo_id
        assert str(payment.price_original) == "139.00"
        assert str(payment.discount_amount) == "20.00"
        assert str(payment.price_final) == "119.00"
        usage = (
            session.query(PromocodeUsage)
            .filter(PromocodeUsage.id == UUID(reserved["reservation_id"]))
            .first()
        )
        assert usage is not None
        assert usage.status == "redeemed"
        assert str(usage.payment_id) == payment_id
        promo = session.query(Promocode).filter(Promocode.id == promo_id).first()
        assert promo is not None
        assert promo.code_left == 4


@pytest.mark.asyncio
async def test_tbank_mark_init_failed_marks_pending_payment(session_factory, whitelist_service):
    user_id = 309
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=1,
        amount_rub=Decimal("29"),
    )
    payment_id = str(intent["payment_id"])
    result = await whitelist_service.mark_tbank_payment_failed(
        payment_id=payment_id,
        reason="init_failed",
        error_meta={"stage": "init"},
    )
    assert result["status"] == "ok"

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        assert payment is not None
        assert payment.status == "init_failed"
        failed_events = (
            session.query(BillingEvent)
            .filter(
                BillingEvent.provider == "tbank_sbp",
                BillingEvent.event_type == "tbank_payment_init_failed",
                BillingEvent.payment_id == UUID(payment_id),
            )
            .all()
        )
        assert len(failed_events) == 1


@pytest.mark.asyncio
async def test_tbank_refund_notification_rolls_back_paid_credits(session_factory, whitelist_service):
    user_id = 310
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=5,
        amount_rub=Decimal("139"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank-payment-refund-1",
        init_meta={"status": "NEW"},
    )
    applied = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-refund-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=13900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-refund-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )
    assert applied["status"] == "applied"
    assert applied["remaining_requests"] == 5

    refunded = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-refund-1",
        status="REFUNDED",
        success=False,
        amount_kopecks=13900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-refund-1", "Status": "REFUNDED"},
        accept_statuses={"CONFIRMED"},
    )
    assert refunded["status"] == "refunded"
    assert refunded["remaining_requests"] == 0
    assert refunded["credits"] == 5

    duplicate_refund = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-refund-1",
        status="REFUNDED",
        success=False,
        amount_kopecks=13900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-refund-1", "Status": "REFUNDED"},
        accept_statuses={"CONFIRMED"},
    )
    assert duplicate_refund["status"] == "duplicate_refund"

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        user = session.query(User).filter(User.user_id == user_id).first()
        assert payment is not None
        assert payment.status == "refunded"
        assert payment.refunded_at is not None
        assert user is not None
        assert user.usage_left == 0
        assert user.credits_status == "exhausted"


@pytest.mark.asyncio
async def test_tbank_refund_notification_marks_pending_when_not_enough_unused_credits(
    session_factory, whitelist_service
):
    user_id = 311
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=10,
        amount_rub=Decimal("269"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank-payment-refund-2",
        init_meta={"status": "NEW"},
    )
    applied = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-refund-2",
        status="CONFIRMED",
        success=True,
        amount_kopecks=26900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-refund-2", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )
    assert applied["status"] == "applied"
    spent = await whitelist_service.reserve_units(user_id, 7)
    assert spent["allowed"] is True
    assert spent["remaining_requests"] == 3

    refund_pending = await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-refund-2",
        status="REFUNDED",
        success=False,
        amount_kopecks=26900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-refund-2", "Status": "REFUNDED"},
        accept_statuses={"CONFIRMED"},
    )
    assert refund_pending["status"] == "refund_pending"
    assert refund_pending["reason"] == "insufficient_unused_credits"
    assert refund_pending["remaining_requests"] == 3
    assert refund_pending["required_credits"] == 10

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        user = session.query(User).filter(User.user_id == user_id).first()
        assert payment is not None
        assert payment.status == "refund_pending"
        assert user is not None
        assert user.usage_left == 3


@pytest.mark.asyncio
async def test_lookup_tbank_payment_by_provider_id(session_factory, whitelist_service):
    user_id = 312
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=1,
        amount_rub=Decimal("29"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank-payment-lookup-1",
        init_meta={"status": "NEW"},
    )
    await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-lookup-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=2900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-lookup-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )
    found = await whitelist_service.lookup_tbank_payment("tbank-payment-lookup-1")
    assert found["status"] == "ok"
    assert found["payment_status"] == "paid"
    assert found["credits_amount"] == 1


@pytest.mark.asyncio
async def test_lookup_tbank_payment_ignores_web_payment(session_factory, whitelist_service):
    provider_payment_id = "tbank-web-payment-lookup-ignore"
    with session_factory() as session:
        payment = Payment(
            user_id=None,
            account_id=uuid4(),
            price_original=Decimal("199"),
            discount_amount=Decimal("0"),
            price_final=Decimal("199"),
            currency="RUB",
            status="paid",
            provider="tbank_sbp",
            provider_payment_id=provider_payment_id,
            credits_amount=1,
        )
        session.add(payment)
        session.commit()

    found = await whitelist_service.lookup_tbank_payment(provider_payment_id)
    assert found["status"] == "not_found"


@pytest.mark.asyncio
async def test_tbank_admin_refund_happy_path(session_factory, whitelist_service):
    user_id = 313
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=5,
        amount_rub=Decimal("139"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank-payment-admin-refund-1",
        init_meta={"status": "NEW"},
    )
    await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-admin-refund-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=13900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-admin-refund-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )

    start = await whitelist_service.start_tbank_refund(payment_id)
    assert start["status"] == "ready"
    assert start["local_mode"] == "refund"
    assert start["remaining_requests"] == 0

    done = await whitelist_service.finalize_tbank_refund(
        payment_id,
        success=True,
        reason="support_case",
        tbank_status="REVERSED",
    )
    assert done["status"] == "applied"
    assert done["mode"] == "refund"
    assert done["remaining_requests"] == 0

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        user = session.query(User).filter(User.user_id == user_id).first()
        assert payment is not None
        assert payment.status == "refunded"
        assert payment.refunded_at is not None
        assert user is not None
        assert user.usage_left == 0


@pytest.mark.asyncio
async def test_tbank_admin_refund_ignores_web_payment(session_factory, whitelist_service):
    with session_factory() as session:
        payment = Payment(
            user_id=None,
            account_id=uuid4(),
            price_original=Decimal("199"),
            discount_amount=Decimal("0"),
            price_final=Decimal("199"),
            currency="RUB",
            status="paid",
            provider="tbank_sbp",
            provider_payment_id="tbank-web-refund-ignore",
            credits_amount=1,
        )
        session.add(payment)
        session.commit()
        payment_id = str(payment.id)

    start = await whitelist_service.start_tbank_refund(payment_id)
    assert start["status"] == "not_found"


@pytest.mark.asyncio
async def test_tbank_admin_cancel_pending_payment(session_factory, whitelist_service):
    user_id = 314
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=1,
        amount_rub=Decimal("29"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank-payment-admin-cancel-1",
        init_meta={"status": "AUTHORIZED"},
    )

    start = await whitelist_service.start_tbank_refund(payment_id)
    assert start["status"] == "ready"
    assert start["local_mode"] == "cancel"

    done = await whitelist_service.finalize_tbank_refund(
        payment_id,
        success=True,
        reason="user_requested",
        tbank_status="CANCELED",
    )
    assert done["status"] == "applied"
    assert done["mode"] == "cancel"

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        user = session.query(User).filter(User.user_id == user_id).first()
        assert payment is not None
        assert payment.status == "canceled"
        assert user is not None
        assert user.usage_left == 0


@pytest.mark.asyncio
async def test_tbank_admin_refund_error_restores_hold(session_factory, whitelist_service):
    user_id = 315
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=5,
        amount_rub=Decimal("139"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank-payment-admin-refund-error",
        init_meta={"status": "NEW"},
    )
    await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank-payment-admin-refund-error",
        status="CONFIRMED",
        success=True,
        amount_kopecks=13900,
        payload={"OrderId": payment_id, "PaymentId": "tbank-payment-admin-refund-error", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )

    start = await whitelist_service.start_tbank_refund(payment_id)
    assert start["status"] == "ready"
    assert start["remaining_requests"] == 0

    failed = await whitelist_service.finalize_tbank_refund(
        payment_id,
        success=False,
        reason="support_case",
        tbank_error="api timeout",
        tbank_status="CONFIRMED",
    )
    assert failed["status"] == "tbank_error"

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.id == UUID(payment_id)).first()
        user = session.query(User).filter(User.user_id == user_id).first()
        assert payment is not None
        assert payment.status == "paid"
        assert user is not None
        assert user.usage_left == 5


@pytest.mark.asyncio
async def test_promocode_reserve_validate_apply_flow(session_factory, whitelist_service):
    user_id = 901
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        promo = Promocode(
            code_string="SALE20",
            discount_type="percent",
            discount_amount=Decimal("20"),
            code_amount=5,
            code_left=5,
            max_uses_per_user=2,
            is_active=True,
        )
        session.add(promo)
        session.commit()
        promo_id = promo.id

    reserved = await whitelist_service.reserve_promocode(
        user_id=user_id,
        code="sale20",
        credits=10,
        stars_original=199,
        ttl_seconds=3600,
    )
    assert reserved["status"] == "ok"
    assert reserved["code_id"] == str(promo_id)
    assert reserved["stars_original"] == 199
    assert reserved["discount_stars"] == 40
    assert reserved["stars_final"] == 159

    valid = await whitelist_service.validate_promocode_reservation(
        reservation_id=reserved["reservation_id"],
        user_id=user_id,
        promo_code_id=reserved["code_id"],
        credits=10,
        stars_original=reserved["stars_original"],
        discount_stars=reserved["discount_stars"],
        stars_final=reserved["stars_final"],
    )
    assert valid["status"] == "ok"

    applied = await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=reserved["stars_final"],
        provider_payment_id="tg:promo-apply-1",
        telegram_payment_charge_id="tg-charge-promo-1",
        promo_reservation_id=reserved["reservation_id"],
        promo_code_id=reserved["code_id"],
        stars_original=reserved["stars_original"],
        discount_stars=reserved["discount_stars"],
    )
    assert applied["status"] == "applied"
    assert applied["remaining_requests"] == 10

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:promo-apply-1").first()
        assert payment is not None
        assert payment.promocode_id == promo_id
        assert int(payment.price_original or 0) == 199
        assert int(payment.discount_amount or 0) == 40
        assert int(payment.price_final or 0) == 159
        usage = (
            session.query(PromocodeUsage)
            .filter(PromocodeUsage.id == UUID(reserved["reservation_id"]))
            .first()
        )
        assert usage is not None
        assert usage.status == "redeemed"
        assert str(usage.payment_id) == str(payment.id)
        promo = session.query(Promocode).filter(Promocode.id == payment.promocode_id).first()
        assert promo is not None
        assert promo.code_left == 4


@pytest.mark.asyncio
async def test_promocode_release_restores_global_slot(session_factory, whitelist_service):
    user_id = 902
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        promo = Promocode(
            code_string="FIXED30",
            discount_type="fixed",
            discount_amount=Decimal("30"),
            code_amount=2,
            code_left=2,
            max_uses_per_user=5,
            is_active=True,
        )
        session.add(promo)
        session.commit()
        promo_id = promo.id

    reserved = await whitelist_service.reserve_promocode(
        user_id=user_id,
        code="fixed30",
        credits=10,
        stars_original=199,
        ttl_seconds=3600,
    )
    assert reserved["status"] == "ok"

    released = await whitelist_service.release_promocode_reservation(
        reserved["reservation_id"],
        user_id=user_id,
        reason="test_clear",
    )
    assert released["status"] == "released"

    with session_factory() as session:
        promo = session.query(Promocode).filter(Promocode.id == promo_id).first()
        usage = (
            session.query(PromocodeUsage)
            .filter(PromocodeUsage.id == UUID(reserved["reservation_id"]))
            .first()
        )
        assert promo is not None
        assert promo.code_left == 2
        assert usage is not None
        assert usage.status == "released"
        assert usage.release_reason == "test_clear"


@pytest.mark.asyncio
async def test_promocode_refund_does_not_restore_usage_slot(session_factory, whitelist_service):
    user_id = 903
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        promo = Promocode(
            code_string="REFUND10",
            discount_type="fixed",
            discount_amount=Decimal("10"),
            code_amount=3,
            code_left=3,
            max_uses_per_user=3,
            is_active=True,
        )
        session.add(promo)
        session.commit()
        promo_id = promo.id

    reserved = await whitelist_service.reserve_promocode(
        user_id=user_id,
        code="refund10",
        credits=5,
        stars_original=109,
        ttl_seconds=3600,
    )
    assert reserved["status"] == "ok"

    applied = await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=5,
        stars_amount=reserved["stars_final"],
        provider_payment_id="tg:promo-refund-1",
        telegram_payment_charge_id="tg-charge-promo-refund-1",
        promo_reservation_id=reserved["reservation_id"],
        promo_code_id=reserved["code_id"],
        stars_original=reserved["stars_original"],
        discount_stars=reserved["discount_stars"],
    )
    assert applied["status"] == "applied"

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:promo-refund-1").first()
        assert payment is not None
        payment_id = str(payment.id)

    assert (await whitelist_service.start_stars_refund(payment_id))["status"] == "ready"
    assert (await whitelist_service.finalize_stars_refund(payment_id, success=True))["status"] == "applied"

    with session_factory() as session:
        promo = session.query(Promocode).filter(Promocode.id == promo_id).first()
        usage = (
            session.query(PromocodeUsage)
            .filter(PromocodeUsage.id == UUID(reserved["reservation_id"]))
            .first()
        )
        assert promo is not None
        assert promo.code_left == 2
        assert usage is not None
        assert usage.status == "redeemed"


@pytest.mark.asyncio
async def test_stars_refund_happy_path(session_factory, whitelist_service):
    user_id = 401
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:refund-happy",
        telegram_payment_charge_id="telegram-refund-happy",
    )

    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:refund-happy").first()
        assert payment is not None
        payment_id = str(payment.id)

    start = await whitelist_service.start_stars_refund(payment_id)
    assert start["status"] == "ready"

    done = await whitelist_service.finalize_stars_refund(
        payment_id,
        success=True,
        reason="support_case",
    )
    assert done["status"] == "applied"
    assert done["remaining_requests"] == 0

    with session_factory() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:refund-happy").first()
        assert user is not None
        assert user.usage_left == 0
        assert user.credits_status == "exhausted"
        assert payment is not None
        assert payment.status == "refunded"
        assert payment.refunded_at is not None
        assert payment.refund_reason == "support_case"


@pytest.mark.asyncio
async def test_stars_refund_duplicate_is_idempotent(session_factory, whitelist_service):
    user_id = 402
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=5,
        stars_amount=109,
        provider_payment_id="tg:refund-dup",
        telegram_payment_charge_id="telegram-refund-dup",
    )
    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:refund-dup").first()
        payment_id = str(payment.id)

    assert (await whitelist_service.start_stars_refund(payment_id))["status"] == "ready"
    assert (await whitelist_service.finalize_stars_refund(payment_id, success=True))["status"] == "applied"
    second = await whitelist_service.start_stars_refund(payment_id)
    assert second["status"] == "duplicate_refund"


@pytest.mark.asyncio
async def test_stars_refund_rejected_when_insufficient_unused_credits(session_factory, whitelist_service):
    user_id = 403
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:refund-low",
        telegram_payment_charge_id="telegram-refund-low",
    )
    await whitelist_service.reserve_units(user_id, 7)
    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:refund-low").first()
        payment_id = str(payment.id)

    start = await whitelist_service.start_stars_refund(payment_id)
    assert start["status"] == "insufficient_unused_credits"
    assert start["remaining_requests"] == 3
    assert start["required_credits"] == 10


@pytest.mark.asyncio
async def test_stars_refund_finalize_error_restores_paid_status(session_factory, whitelist_service):
    user_id = 404
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:refund-error",
        telegram_payment_charge_id="telegram-refund-error",
    )
    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:refund-error").first()
        payment_id = str(payment.id)

    assert (await whitelist_service.start_stars_refund(payment_id))["status"] == "ready"
    failed = await whitelist_service.finalize_stars_refund(
        payment_id,
        success=False,
        telegram_error="api timeout",
    )
    assert failed["status"] == "telegram_error"

    with session_factory() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:refund-error").first()
        assert user is not None
        assert user.usage_left == 10
        assert payment is not None
        assert payment.status == "paid"
        assert payment.refunded_at is None


@pytest.mark.asyncio
async def test_stars_refund_concurrent_start_returns_in_progress(session_factory, whitelist_service):
    user_id = 405
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:refund-progress",
        telegram_payment_charge_id="telegram-refund-progress",
    )
    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:refund-progress").first()
        payment_id = str(payment.id)

    first = await whitelist_service.start_stars_refund(payment_id)
    second = await whitelist_service.start_stars_refund(payment_id)
    assert first["status"] == "ready"
    assert second["status"] == "in_progress"


@pytest.mark.asyncio
async def test_billing_report_summary_counts(whitelist_service):
    user_id = 501
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:report-1",
        telegram_payment_charge_id="telegram-report-1",
    )
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:report-1",
        telegram_payment_charge_id="telegram-report-1",
    )
    await whitelist_service.record_billing_event(
        provider="telegram_stars",
        event_type="stars_payment_invalid",
        user_id=user_id,
        reason="manual_test",
    )
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=1,
        amount_rub=Decimal("29"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank:report-1",
        init_meta={"status": "NEW"},
    )
    await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank:report-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=2900,
        payload={"OrderId": payment_id, "PaymentId": "tbank:report-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )
    report = await whitelist_service.get_billing_report(days=7)
    summary = report["summary"]
    assert summary["paid"] >= 2
    assert summary["duplicate"] >= 1
    assert summary["invalid"] >= 1
    breakdown = report.get("payment_breakdown") or []
    assert any(
        item.get("provider") == "tbank_sbp" and item.get("status") == "paid"
        for item in breakdown
    )
    invalid_reasons = report.get("invalid_reason_counts", {})
    assert invalid_reasons.get("manual_test", 0) >= 1


@pytest.mark.asyncio
async def test_billing_user_report_includes_tbank_and_stars(whitelist_service):
    user_id = 511
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=1,
        stars_amount=25,
        provider_payment_id="tg:user-report-1",
        telegram_payment_charge_id="tg-charge-user-report-1",
    )
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=5,
        amount_rub=Decimal("139"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank:user-report-1",
        init_meta={"status": "NEW"},
    )
    await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank:user-report-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=13900,
        payload={"OrderId": payment_id, "PaymentId": "tbank:user-report-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )
    report = await whitelist_service.get_billing_user_report(user_id=user_id, days=7)
    payments = report.get("payments") or []
    assert any(item.get("provider") == "telegram_stars" for item in payments)
    assert any(item.get("provider") == "tbank_sbp" for item in payments)


@pytest.mark.asyncio
async def test_tbank_billing_event_amount_saved_in_rub_units(session_factory, whitelist_service):
    user_id = 514
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=1,
        amount_rub=Decimal("29"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank:rub-units-1",
        init_meta={"status": "NEW"},
    )
    await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank:rub-units-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=2900,
        payload={"OrderId": payment_id, "PaymentId": "tbank:rub-units-1", "Status": "CONFIRMED"},
        accept_statuses={"CONFIRMED"},
    )

    with session_factory() as session:
        event = (
            session.query(BillingEvent)
            .filter(
                BillingEvent.provider == "tbank_sbp",
                BillingEvent.event_type == "tbank_payment_paid",
                BillingEvent.payment_id == UUID(payment_id),
            )
            .order_by(BillingEvent.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.currency == "RUB"
        assert int(event.stars_amount or 0) == 29
        assert str(event.provider_amount) == "29.00"


@pytest.mark.asyncio
async def test_tbank_billing_event_amount_keeps_decimal_provider_amount(
    session_factory, whitelist_service
):
    user_id = 515
    await whitelist_service.ensure_user(user_id)
    intent = await whitelist_service.create_tbank_payment_intent(
        user_id=user_id,
        credits=1,
        amount_rub=Decimal("26.10"),
    )
    payment_id = str(intent["payment_id"])
    await whitelist_service.mark_tbank_payment_initialized(
        payment_id=payment_id,
        provider_payment_id="tbank:rub-decimal-1",
        init_meta={"status": "NEW"},
    )
    await whitelist_service.apply_tbank_notification(
        order_id=payment_id,
        provider_payment_id="tbank:rub-decimal-1",
        status="CONFIRMED",
        success=True,
        amount_kopecks=2610,
        payload={
            "OrderId": payment_id,
            "PaymentId": "tbank:rub-decimal-1",
            "Status": "CONFIRMED",
        },
        accept_statuses={"CONFIRMED"},
    )

    with session_factory() as session:
        event = (
            session.query(BillingEvent)
            .filter(
                BillingEvent.provider == "tbank_sbp",
                BillingEvent.event_type == "tbank_payment_paid",
                BillingEvent.payment_id == UUID(payment_id),
            )
            .order_by(BillingEvent.created_at.desc())
            .first()
        )
        assert event is not None
        assert event.currency == "RUB"
        # Legacy integer field keeps major units for compatibility.
        assert int(event.stars_amount or 0) == 26
        # Exact provider amount keeps decimals for discounts/promocodes.
        assert str(event.provider_amount) == "26.10"


@pytest.mark.asyncio
async def test_billing_reconciliation_detects_mismatch_and_honors_admin_grants(
    session_factory, whitelist_service
):
    mismatch_user = 512
    await whitelist_service.ensure_user(mismatch_user)
    await whitelist_service.apply_stars_payment(
        user_id=mismatch_user,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:reconcile-mismatch-1",
        telegram_payment_charge_id="tg-charge-reconcile-mismatch-1",
    )
    await whitelist_service.reserve_units(mismatch_user, 2)
    with session_factory() as session:
        user = session.query(User).filter(User.user_id == mismatch_user).first()
        assert user is not None
        user.usage_left = 1
        session.commit()

    balanced_user = 513
    await whitelist_service.add_user_to_whitelist(balanced_user, requests=100)

    report = await whitelist_service.get_billing_reconciliation(limit_users=10, min_abs_delta=1)
    assert report["users_checked"] >= 2
    assert report["mismatches_total"] >= 1
    mismatch_rows = [item for item in report["mismatches"] if int(item["user_id"]) == mismatch_user]
    assert mismatch_rows
    assert int(mismatch_rows[0]["delta"]) == -7
    balanced_rows = [item for item in report["mismatches"] if int(item["user_id"]) == balanced_user]
    assert not balanced_rows


@pytest.mark.asyncio
async def test_webhook_event_registry_idempotency_and_dead_letter(session_factory, whitelist_service):
    payload = {
        "OrderId": "abcd",
        "PaymentId": "pid-1",
        "Status": "CONFIRMED",
        "Success": True,
        "Amount": 2900,
    }
    first = await whitelist_service.register_webhook_event(
        provider="tbank_sbp",
        event_type="payment_notification",
        idempotency_key="idem-1",
        order_id="abcd",
        provider_payment_id="pid-1",
        payload=payload,
        max_attempts=2,
    )
    assert first["status"] == "accepted"
    assert first["should_process"] is True
    event_id = str(first["event_id"])

    done = await whitelist_service.finalize_webhook_event(
        event_id=event_id,
        status="processed",
    )
    assert done["status"] == "ok"

    dup = await whitelist_service.register_webhook_event(
        provider="tbank_sbp",
        event_type="payment_notification",
        idempotency_key="idem-1",
        order_id="abcd",
        provider_payment_id="pid-1",
        payload=payload,
        max_attempts=2,
    )
    assert dup["status"] == "duplicate"
    assert dup["should_process"] is False

    dl1 = await whitelist_service.register_webhook_event(
        provider="tbank_sbp",
        event_type="payment_notification",
        idempotency_key="idem-2",
        order_id="abcd",
        provider_payment_id="pid-2",
        payload=payload,
        max_attempts=1,
    )
    assert dl1["status"] == "accepted"
    await whitelist_service.finalize_webhook_event(
        event_id=str(dl1["event_id"]),
        status="failed",
        error="network",
    )
    dl2 = await whitelist_service.register_webhook_event(
        provider="tbank_sbp",
        event_type="payment_notification",
        idempotency_key="idem-2",
        order_id="abcd",
        provider_payment_id="pid-2",
        payload=payload,
        max_attempts=1,
    )
    assert dl2["status"] == "dead_letter"
    assert dl2["should_process"] is False

    listed = await whitelist_service.list_webhook_dead_letters(provider="tbank_sbp", limit=20)
    assert listed["status"] == "ok"
    assert any(item["event_id"] == str(dl1["event_id"]) for item in listed["items"])

    with session_factory() as session:
        event = (
            session.query(BillingWebhookEvent)
            .filter(BillingWebhookEvent.id == UUID(str(dl1["event_id"])))
            .first()
        )
        assert event is not None
        assert event.status == "dead_letter"


@pytest.mark.asyncio
async def test_billing_suspicious_detects_old_refund_pending(session_factory, whitelist_service):
    user_id = 502
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:susp-1",
        telegram_payment_charge_id="telegram-susp-1",
    )
    with session_factory() as session:
        payment = session.query(Payment).filter(Payment.provider_payment_id == "tg:susp-1").first()
        assert payment is not None
        payment.status = "refund_pending"
        payment.created_at = utcnow() - timedelta(minutes=20)
        session.commit()

    report = await whitelist_service.get_billing_suspicious(days=7, refund_pending_minutes=10)
    kinds = {item["kind"] for item in report["issues"]}
    assert "refund_pending_too_long" in kinds


@pytest.mark.asyncio
async def test_billing_suspicious_usage_left_mismatch_uses_full_ledger(session_factory, whitelist_service):
    user_id = 503
    await whitelist_service.ensure_user(user_id)
    await whitelist_service.apply_stars_payment(
        user_id=user_id,
        credits=10,
        stars_amount=199,
        provider_payment_id="tg:susp-mismatch-full-ledger",
        telegram_payment_charge_id="telegram-susp-mismatch-full-ledger",
    )
    await whitelist_service.reserve_units(user_id, 1)
    with session_factory() as session:
        paid_event = (
            session.query(BillingEvent)
            .filter(
                BillingEvent.user_id == user_id,
                BillingEvent.event_type == "stars_payment_paid",
            )
            .first()
        )
        assert paid_event is not None
        paid_event.created_at = utcnow() - timedelta(days=30)
        session.commit()

    report = await whitelist_service.get_billing_suspicious(days=7, refund_pending_minutes=10)
    mismatch_for_user = [
        item
        for item in report["issues"]
        if item.get("kind") == "usage_left_mismatch" and int(item.get("user_id", 0)) == user_id
    ]
    assert not mismatch_for_user


@pytest.mark.asyncio
async def test_billing_suspicious_skips_legacy_users_without_inflow_events(
    session_factory, whitelist_service
):
    user_id = 504
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        assert user is not None
        user.usage_left = 999
        user.credits_status = "active"
        session.commit()
    await whitelist_service.record_billing_event(
        provider="telegram_stars",
        event_type="credits_spent",
        user_id=user_id,
        credits_amount=1,
    )

    report = await whitelist_service.get_billing_suspicious(days=7, refund_pending_minutes=10)
    mismatch_for_user = [
        item
        for item in report["issues"]
        if item.get("kind") == "usage_left_mismatch" and int(item.get("user_id", 0)) == user_id
    ]
    assert not mismatch_for_user


@pytest.mark.asyncio
async def test_new_users_only_promocode_allows_user_without_paid_history(session_factory, whitelist_service):
    user_id = 904
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        promo = Promocode(
            code_string="NEW15",
            discount_type="percent",
            discount_amount=Decimal("15"),
            code_amount=10,
            code_left=10,
            max_uses_per_user=1,
            is_new_users_only=True,
            is_active=True,
        )
        session.add(promo)
        session.commit()

    check = await whitelist_service.check_promocode(user_id, "NEW15")
    assert check["status"] == "ok"
    assert check["is_new_users_only"] is True

    reserved = await whitelist_service.reserve_promocode(
        user_id=user_id,
        code="NEW15",
        credits=10,
        stars_original=199,
        ttl_seconds=3600,
    )
    assert reserved["status"] == "ok"


@pytest.mark.asyncio
async def test_promocode_reservation_does_not_consume_max_uses_before_payment(
    session_factory, whitelist_service
):
    user_id = 9041
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        promo = Promocode(
            code_string="TRY15",
            discount_type="percent",
            discount_amount=Decimal("15"),
            code_amount=10,
            code_left=10,
            max_uses_per_user=1,
            is_active=True,
        )
        session.add(promo)
        session.commit()

    first_check = await whitelist_service.check_promocode(user_id, "TRY15")
    assert first_check["status"] == "ok"

    first_reserved = await whitelist_service.reserve_promocode(
        user_id=user_id,
        code="TRY15",
        credits=5,
        stars_original=139,
        ttl_seconds=3600,
    )
    assert first_reserved["status"] == "ok"

    second_check = await whitelist_service.check_promocode(user_id, "TRY15")
    assert second_check["status"] == "ok"

    second_reserved = await whitelist_service.reserve_promocode(
        user_id=user_id,
        code="TRY15",
        credits=10,
        stars_original=199,
        ttl_seconds=3600,
        previous_reservation_id=str(first_reserved["reservation_id"]),
    )
    assert second_reserved["status"] == "ok"

    with session_factory() as session:
        usages = (
            session.query(PromocodeUsage)
            .filter(PromocodeUsage.user_id == user_id)
            .order_by(PromocodeUsage.reserved_at.asc())
            .all()
        )
        assert len(usages) == 1
        assert usages[0].status == "reserved"
        assert int(usages[0].credits_amount or 0) == 10
        assert int(Decimal(usages[0].price_final or 0)) == int(second_reserved["stars_final"])


@pytest.mark.asyncio
async def test_new_users_only_promocode_rejects_user_with_paid_history(session_factory, whitelist_service):
    user_id = 905
    await whitelist_service.ensure_user(user_id)
    with session_factory() as session:
        promo = Promocode(
            code_string="FIRSTONLY",
            discount_type="percent",
            discount_amount=Decimal("15"),
            code_amount=10,
            code_left=10,
            max_uses_per_user=1,
            is_new_users_only=True,
            is_active=True,
        )
        session.add(promo)
        session.flush()

        payment = Payment(
            user_id=user_id,
            provider="telegram_stars",
            provider_payment_id="tg:old-paid-user",
            telegram_payment_charge_id="tg-charge-old-paid-user",
            credits_amount=5,
            price_original=Decimal("109"),
            discount_amount=Decimal("0"),
            price_final=Decimal("109"),
            currency="XTR",
            status="paid",
            paid_at=utcnow(),
        )
        session.add(payment)
        session.commit()

    check = await whitelist_service.check_promocode(user_id, "FIRSTONLY")
    assert check["status"] == "invalid"
    assert check["reason"] == "new_users_only"

    reserved = await whitelist_service.reserve_promocode(
        user_id=user_id,
        code="FIRSTONLY",
        credits=10,
        stars_original=199,
        ttl_seconds=3600,
    )
    assert reserved["status"] == "invalid"
    assert reserved["reason"] == "new_users_only"
