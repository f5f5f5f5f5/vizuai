from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UUID, UniqueConstraint, func
from sqlalchemy.orm import relationship

from models.base import Base


class ApiIdempotencyKey(Base):
    __tablename__ = "api_idempotency_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    scope = Column(String(64), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False, default="processing", index=True)
    response_status = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("account_id", "scope", "idempotency_key", name="uq_api_idempotency_keys_scope"),
    )

    account = relationship("Account")
