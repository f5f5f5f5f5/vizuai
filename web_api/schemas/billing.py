"""Billing API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BillingPlanResponse(BaseModel):
    provider: str
    credits: int
    currency: str
    amount: str


class BillingCheckoutCreateRequest(BaseModel):
    credits: int
    provider: str = "tbank_sbp"
    promocode: str | None = None


class BillingPromocodeCheckRequest(BaseModel):
    credits: int
    promocode: str
    provider: str = "tbank_sbp"


class BillingPromocodeCheckResponse(BaseModel):
    code: str
    discount_type: str
    discount_value: str
    credits_amount: int
    currency: str
    amount_original: str
    discount_amount: str
    amount_final: str
    code_left: int | None = None


class BillingPaymentResponse(BaseModel):
    id: str
    provider: str | None = None
    status: str
    credits_amount: int
    currency: str
    price_original: str
    discount_amount: str
    price_final: str
    provider_payment_id: str | None = None
    checkout_session_id: str | None = None
    promocode_code: str | None = None
    created_at: datetime
    paid_at: datetime | None = None
    refunded_at: datetime | None = None


class BillingCheckoutResponse(BaseModel):
    id: str
    provider: str
    status: str
    credits_amount: int
    currency: str
    amount_original: str | None = None
    discount_amount: str | None = None
    amount_final: str | None = None
    provider_checkout_id: str | None = None
    checkout_url: str | None = None
    promocode_code: str | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    expires_at: datetime | None = None
    payment: BillingPaymentResponse | None = None
