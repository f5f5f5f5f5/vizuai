from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, UUID, UniqueConstraint, func
from sqlalchemy.orm import relationship

from models.base import Base


class AccountIdentity(Base):
    __tablename__ = "account_identities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    provider = Column(String(32), nullable=False, index=True)
    provider_user_id = Column(String(255), nullable=False)
    provider_email = Column(String(320), nullable=True, index=True)
    provider_phone = Column(String(32), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    is_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "provider_user_id", name="uq_account_identities_provider_user"),
    )

    account = relationship("Account", back_populates="identities")
