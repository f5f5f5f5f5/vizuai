from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class AccountMagicLinkToken(Base):
    __tablename__ = "account_magic_link_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True, index=True)
    email = Column(String(320), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    redirect_path = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)

    account = relationship("Account")
