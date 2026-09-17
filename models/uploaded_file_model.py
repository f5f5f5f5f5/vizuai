from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    purpose = Column(String(32), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    content_type = Column(String(128), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    storage_key = Column(String(1024), nullable=False, unique=True)
    file_url = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="ready", index=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)

    account = relationship("Account", back_populates="uploaded_files")
