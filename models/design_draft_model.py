from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class DesignDraft(Base):
    __tablename__ = "design_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("uploaded_files.id"), nullable=True, index=True)
    style_reference_file_id = Column(
        UUID(as_uuid=True), ForeignKey("uploaded_files.id"), nullable=True, index=True
    )
    source_image_url = Column(Text, nullable=False)
    prepared_image_url = Column(Text, nullable=True)
    style_reference_image_url = Column(Text, nullable=True)
    style_reference_enabled = Column(Boolean, nullable=False, default=False)
    user_request = Column(Text, nullable=False)
    settings_json = Column(JSON, nullable=True)
    estimated_units = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    account = relationship("Account", back_populates="design_drafts")
    source_file = relationship("UploadedFile", foreign_keys=[source_file_id])
    style_reference_file = relationship("UploadedFile", foreign_keys=[style_reference_file_id])
    designs = relationship("Design", back_populates="draft")
