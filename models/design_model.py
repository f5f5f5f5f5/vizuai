from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Boolean,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Integer,
    Text,
    UUID,
    func,
)
from sqlalchemy.orm import relationship

from models.base import Base


class Design(Base):
    __tablename__ = "designs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(BigInteger, ForeignKey("users.user_id"), index=True)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True, index=True)
    original_image_url = Column(Text, nullable=False)
    prepared_image_url = Column(Text, nullable=True)
    render_image_url = Column(Text, nullable=True)
    fix_image_url = Column(Text, nullable=True)
    final_image_url = Column(Text, nullable=True)
    style_reference_image_url = Column(Text, nullable=True)
    style_reference_used = Column(Boolean, nullable=False, default=False)
    style_reference_status = Column(String(32), nullable=True)
    selected_image = Column(String(16), nullable=True)
    user_request = Column(Text, nullable=False)
    status = Column(String(32), default="pending")
    error_message = Column(Text, nullable=True)
    error_stage = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=func.now())
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    cost_usd = Column(Numeric(10, 4), nullable=True)
    score_render = Column(Integer, nullable=True)
    score_fix = Column(Integer, nullable=True)
    providers_json = Column(JSON, nullable=True)
    debug_json = Column(JSON, nullable=True)
    pipeline_version = Column(String(64), nullable=True)
    mode = Column(String(32), nullable=False, default="full")
    units_spent = Column(Integer, nullable=True)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True, index=True)
    draft_id = Column(UUID(as_uuid=True), ForeignKey("design_drafts.id"), nullable=True, index=True)
    metadata_json = Column("metadata", JSON, nullable=True)

    user = relationship("User", back_populates="designs")
    account = relationship("Account", back_populates="designs")
    job = relationship("Job", back_populates="designs")
    draft = relationship("DesignDraft", back_populates="designs")
