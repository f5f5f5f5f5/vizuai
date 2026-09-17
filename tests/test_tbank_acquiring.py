from decimal import Decimal

import pytest

from config import Settings
from services.tbank_acquiring import TBankAcquiringService


def _build_settings(**overrides) -> Settings:
    data = {
        "TELEGRAM_TOKEN": "token",
        "TBANK_TERMINAL_KEY": "demo_terminal",
        "TBANK_PASSWORD": "demo_password",
        "WORKER_PUBLIC_BASE_URL": "https://worker.example.com",
        "TBANK_NOTIFICATION_PATH": "/payments/tbank/notify",
    }
    data.update(overrides)
    return Settings(**data)


@pytest.mark.asyncio
async def test_init_payment_without_receipt_by_default():
    settings = _build_settings()
    service = TBankAcquiringService(settings)
    captured: dict[str, object] = {}

    async def fake_post(method: str, payload: dict[str, object]) -> dict[str, object]:
        captured["method"] = method
        captured["payload"] = payload
        return {
            "Success": True,
            "PaymentURL": "https://pay.example.com/1",
            "PaymentId": "123",
            "Status": "NEW",
        }

    service._post = fake_post  # type: ignore[method-assign]
    result = await service.init_payment(
        order_id="order-1",
        amount_rub=Decimal("269"),
        description="VizuAI top-up",
        customer_key="421936302",
    )
    assert result.payment_id == "123"
    assert result.payment_url == "https://pay.example.com/1"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert "Receipt" not in payload


@pytest.mark.asyncio
async def test_init_payment_includes_receipt_when_enabled():
    settings = _build_settings(
        TBANK_RECEIPT_ENABLED=True,
        TBANK_RECEIPT_EMAIL="payments@vizu.ai",
        TBANK_RECEIPT_FFD_VERSION="1.2",
        TBANK_RECEIPT_TAXATION="usn_income",
        TBANK_RECEIPT_ITEM_NAME="Пополнение баланса VizuAI",
        TBANK_RECEIPT_ITEM_PAYMENT_METHOD="full_payment",
        TBANK_RECEIPT_ITEM_PAYMENT_OBJECT="service",
    )
    service = TBankAcquiringService(settings)
    captured: dict[str, object] = {}

    async def fake_post(method: str, payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "Success": True,
            "PaymentURL": "https://pay.example.com/2",
            "PaymentId": "124",
            "Status": "NEW",
        }

    service._post = fake_post  # type: ignore[method-assign]
    await service.init_payment(
        order_id="order-2",
        amount_rub=Decimal("519"),
        description="VizuAI top-up",
    )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    receipt = payload.get("Receipt")
    assert isinstance(receipt, dict)
    assert receipt.get("Email") == "payments@vizu.ai"
    assert receipt.get("Taxation") == "usn_income"
    assert receipt.get("FfdVersion") == "1.2"
    items = receipt.get("Items")
    assert isinstance(items, list)
    assert int(items[0]["Amount"]) == 51900
    assert items[0].get("PaymentMethod") == "full_payment"
    assert items[0].get("PaymentObject") == "service"


@pytest.mark.asyncio
async def test_init_payment_receipt_omits_optional_fields_when_not_set():
    settings = _build_settings(
        TBANK_RECEIPT_ENABLED=True,
        TBANK_RECEIPT_EMAIL="payments@vizu.ai",
        TBANK_RECEIPT_FFD_VERSION=None,
        TBANK_RECEIPT_ITEM_PAYMENT_METHOD=None,
        TBANK_RECEIPT_ITEM_PAYMENT_OBJECT=None,
    )
    service = TBankAcquiringService(settings)
    captured: dict[str, object] = {}

    async def fake_post(method: str, payload: dict[str, object]) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "Success": True,
            "PaymentURL": "https://pay.example.com/2",
            "PaymentId": "124",
            "Status": "NEW",
        }

    service._post = fake_post  # type: ignore[method-assign]
    await service.init_payment(
        order_id="order-2b",
        amount_rub=Decimal("519"),
        description="VizuAI top-up",
    )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    receipt = payload.get("Receipt")
    assert isinstance(receipt, dict)
    assert "FfdVersion" not in receipt
    items = receipt.get("Items")
    assert isinstance(items, list)
    assert "PaymentMethod" not in items[0]
    assert "PaymentObject" not in items[0]


@pytest.mark.asyncio
async def test_init_payment_receipt_enabled_requires_contact():
    settings = _build_settings(
        TBANK_RECEIPT_ENABLED=True,
        TBANK_RECEIPT_EMAIL="",
        TBANK_RECEIPT_PHONE="",
    )
    service = TBankAcquiringService(settings)
    with pytest.raises(RuntimeError):
        await service.init_payment(
            order_id="order-3",
            amount_rub=Decimal("139"),
            description="VizuAI top-up",
        )


@pytest.mark.asyncio
async def test_get_state_calls_expected_method():
    settings = _build_settings()
    service = TBankAcquiringService(settings)
    captured: dict[str, object] = {}

    async def fake_post(method: str, payload: dict[str, object]) -> dict[str, object]:
        captured["method"] = method
        captured["payload"] = payload
        return {"Success": True, "PaymentId": "777", "Status": "CONFIRMED"}

    service._post = fake_post  # type: ignore[method-assign]
    result = await service.get_state(payment_id="777")
    assert result["success"] is True
    assert result["status"] == "CONFIRMED"
    assert captured["method"] == "GetState"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload.get("PaymentId") == "777"
    assert isinstance(payload.get("Token"), str)


@pytest.mark.asyncio
async def test_cancel_payment_sends_amount_when_provided():
    settings = _build_settings()
    service = TBankAcquiringService(settings)
    captured: dict[str, object] = {}

    async def fake_post(method: str, payload: dict[str, object]) -> dict[str, object]:
        captured["method"] = method
        captured["payload"] = payload
        return {"Success": True, "PaymentId": "778", "Status": "REVERSED"}

    service._post = fake_post  # type: ignore[method-assign]
    result = await service.cancel_payment(payment_id="778", amount_kopecks=2900)
    assert result["success"] is True
    assert captured["method"] == "Cancel"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload.get("PaymentId") == "778"
    assert int(payload.get("Amount")) == 2900
