from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    status = Column(String(32), nullable=False, default="active", index=True)
    display_name = Column(String(128), nullable=True)
    primary_email = Column(String(320), nullable=True, index=True)
    primary_phone = Column(String(32), nullable=True)
    avatar_url = Column(String(1024), nullable=True)
    marketing_opt_in = Column(Boolean, nullable=False, default=False)
    locale = Column(String(16), nullable=True)
    timezone = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    last_seen_at = Column(DateTime, nullable=True)

    identities = relationship("AccountIdentity", back_populates="account")
    sessions = relationship("AccountSession", back_populates="account")
    design_drafts = relationship("DesignDraft", back_populates="account")
    furniture_search_drafts = relationship("FurnitureSearchDraft", back_populates="account")
    jobs = relationship("Job", back_populates="account")
    checkout_sessions = relationship("CheckoutSession", back_populates="account")
    flow_events = relationship("AccountFlowEvent", back_populates="account")
    designs = relationship("Design", back_populates="account")
    payments = relationship("Payment", back_populates="account")
    billing_events = relationship("BillingEvent", back_populates="account")
    uploaded_files = relationship("UploadedFile", back_populates="account")
    upload_intents = relationship("UploadIntent", back_populates="account")
    promocode_usages = relationship("PromocodeUsage", back_populates="account")
    acquisition_attributions = relationship("WebAcquisitionAttribution", back_populates="account")
