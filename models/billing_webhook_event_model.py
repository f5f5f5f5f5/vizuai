from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, String, Text, UUID, UniqueConstraint, func

from models.base import Base


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "idempotency_key", name="uq_billing_webhook_provider_idem"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider = Column(String(32), nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    idempotency_key = Column(String(191), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="received", index=True)
    attempts = Column(Integer, nullable=False, default=1)
    order_id = Column(String(128), nullable=True, index=True)
    provider_payment_id = Column(String(128), nullable=True, index=True)
    payload_json = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    first_seen_at = Column(DateTime, nullable=False, default=func.now())
    last_seen_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    processed_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now(), index=True)
