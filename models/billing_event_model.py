from uuid import uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider = Column(String(32), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=True, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True, index=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True, index=True)
    provider_payment_id = Column(String(128), nullable=True, index=True)
    telegram_payment_charge_id = Column(String(128), nullable=True, index=True)
    currency = Column(String(8), nullable=True)
    stars_amount = Column(Integer, nullable=True)
    provider_amount = Column(Numeric(10, 2), nullable=True)
    credits_amount = Column(Integer, nullable=True)
    reason = Column(String(128), nullable=True, index=True)
    meta_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)

    user = relationship("User")
    account = relationship("Account", back_populates="billing_events")
    payment = relationship("Payment")
