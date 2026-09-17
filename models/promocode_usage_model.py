from uuid import uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, Numeric, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class PromocodeUsage(Base):
    __tablename__ = "promocode_usages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code_id = Column(UUID(as_uuid=True), ForeignKey("promocodes.id"), index=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), index=True, nullable=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), index=True, nullable=True)
    status = Column(String(32), nullable=False, default="redeemed", index=True)
    reserved_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    released_at = Column(DateTime, nullable=True)
    redeemed_at = Column(DateTime, nullable=True)
    release_reason = Column(String(64), nullable=True)
    credits_amount = Column(Integer, nullable=True)
    price_original = Column(Numeric(10, 2), nullable=True)
    discount_amount = Column(Numeric(10, 2), nullable=True)
    price_final = Column(Numeric(10, 2), nullable=True)
    used_at = Column(DateTime, default=func.now())

    promocode = relationship("Promocode", back_populates="usages")
    user = relationship("User")
    account = relationship("Account", back_populates="promocode_usages")
    payment = relationship("Payment", back_populates="usages")
