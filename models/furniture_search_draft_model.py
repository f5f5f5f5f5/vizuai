from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class FurnitureSearchDraft(Base):
    __tablename__ = "furniture_search_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    source_file_id = Column(UUID(as_uuid=True), ForeignKey("uploaded_files.id"), nullable=True, index=True)
    source_image_url = Column(Text, nullable=False)
    prepared_image_url = Column(Text, nullable=True)
    user_request = Column(Text, nullable=True)
    settings_json = Column(JSON, nullable=True)
    estimated_units = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    account = relationship("Account", back_populates="furniture_search_drafts")
    source_file = relationship("UploadedFile", foreign_keys=[source_file_id])
