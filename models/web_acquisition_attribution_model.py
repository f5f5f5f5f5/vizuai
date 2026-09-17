from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class WebAcquisitionAttribution(Base):
    __tablename__ = "web_acquisition_attributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    anon_id = Column(String(64), nullable=False, unique=True, index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True, index=True)
    first_utm_source = Column(String(255), nullable=True, index=True)
    first_utm_medium = Column(String(255), nullable=True, index=True)
    first_utm_campaign = Column(String(255), nullable=True, index=True)
    first_utm_content = Column(String(255), nullable=True)
    first_utm_term = Column(String(255), nullable=True)
    first_landing_host = Column(String(255), nullable=True)
    first_landing_path = Column(String(255), nullable=True)
    first_referrer = Column(String(1024), nullable=True)
    first_seen_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    last_seen_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    linked_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    account = relationship("Account", back_populates="acquisition_attributions")
