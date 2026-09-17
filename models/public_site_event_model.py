from uuid import uuid4

from sqlalchemy import Column, DateTime, String, Text, UUID, func

from models.base import Base


class PublicSiteEvent(Base):
    __tablename__ = "public_site_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    anon_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    screen_key = Column(String(64), nullable=True, index=True)
    action_key = Column(String(128), nullable=True, index=True)
    source = Column(String(64), nullable=True, index=True)
    path = Column(String(255), nullable=True, index=True)
    referrer = Column(String(255), nullable=True)
    meta_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)
