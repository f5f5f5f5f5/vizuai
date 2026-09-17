from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class UploadIntent(Base):
    __tablename__ = "upload_intents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    purpose = Column(String(32), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_key = Column(String(1024), nullable=False, unique=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    expires_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    file_id = Column(UUID(as_uuid=True), ForeignKey("uploaded_files.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    account = relationship("Account", back_populates="upload_intents")
    file = relationship("UploadedFile")
