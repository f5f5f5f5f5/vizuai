from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class Promocode(Base):
    __tablename__ = "promocodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code_string = Column(String(64), nullable=False, unique=True)
    discount_type = Column(String(16), nullable=False)
    discount_amount = Column(Numeric(10, 2), nullable=False)
    code_amount = Column(Integer, nullable=True)
    code_left = Column(Integer, nullable=True)
    max_uses_per_user = Column(Integer, nullable=True)
    is_new_users_only = Column(Boolean, nullable=False, default=False)
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    payments = relationship("Payment", back_populates="promocode")
    usages = relationship("PromocodeUsage", back_populates="promocode")
