from uuid import uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), index=True, nullable=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=True)
    checkout_session_id = Column(
        UUID(as_uuid=True), ForeignKey("checkout_sessions.id"), index=True, nullable=True
    )
    promocode_id = Column(UUID(as_uuid=True), ForeignKey("promocodes.id"), index=True, nullable=True)
    price_original = Column(Numeric(10, 2), nullable=False)
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0)
    price_final = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="RUB")
    status = Column(String(32), nullable=False, default="pending", index=True)
    provider = Column(String(32), nullable=True)
    provider_payment_id = Column(String(128), nullable=True, index=True)
    telegram_payment_charge_id = Column(String(128), nullable=True, index=True)
    credits_amount = Column(Integer, nullable=False, default=0)
    refund_reason = Column(String(256), nullable=True)
    created_at = Column(DateTime, default=func.now())
    paid_at = Column(DateTime, nullable=True)
    refunded_at = Column(DateTime, nullable=True)

    user = relationship("User")
    account = relationship("Account", back_populates="payments")
    checkout_session = relationship("CheckoutSession", back_populates="payments")
    promocode = relationship("Promocode", back_populates="payments")
    usages = relationship("PromocodeUsage", back_populates="payment")
