from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, UUID, func
from sqlalchemy.orm import relationship

from models.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    job_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="queued", index=True)
    draft_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    draft_type = Column(String(32), nullable=True)
    result_ref_type = Column(String(32), nullable=True)
    result_ref_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    error_code = Column(String(64), nullable=True, index=True)
    error_message = Column(Text, nullable=True)
    error_stage = Column(String(64), nullable=True)
    units_reserved = Column(Integer, nullable=False, default=0)
    units_final = Column(Integer, nullable=True)
    provider_meta_json = Column(JSON, nullable=True)
    progress_meta_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)

    account = relationship("Account", back_populates="jobs")
    designs = relationship("Design", back_populates="job")
