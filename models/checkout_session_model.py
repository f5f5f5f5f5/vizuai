from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class CheckoutSession(Base):
    __tablename__ = "checkout_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    credits_amount = Column(Integer, nullable=False, default=0)
    currency = Column(String(8), nullable=False, default="RUB")
    amount_original = Column(Numeric(10, 2), nullable=True)
    discount_amount = Column(Numeric(10, 2), nullable=True)
    amount_final = Column(Numeric(10, 2), nullable=True)
    provider_checkout_id = Column(String(128), nullable=True, index=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    account = relationship("Account", back_populates="checkout_sessions")
    payments = relationship("Payment", back_populates="checkout_session")
