from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, JSON, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class AccountSession(Base):
    __tablename__ = "account_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    session_token_hash = Column(String(255), nullable=False, unique=True, index=True)
    refresh_token_hash = Column(String(255), nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    user_agent = Column(String(1024), nullable=True)
    ip_address = Column(String(64), nullable=True)
    device_meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    last_seen_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    account = relationship("Account", back_populates="sessions")
