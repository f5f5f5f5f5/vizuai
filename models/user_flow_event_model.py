from uuid import uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class UserFlowEvent(Base):
    __tablename__ = "user_flow_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), nullable=False, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    screen_key = Column(String(64), nullable=True, index=True)
    action_key = Column(String(128), nullable=True, index=True)
    source = Column(String(64), nullable=True, index=True)
    meta_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)

    user = relationship("User")
