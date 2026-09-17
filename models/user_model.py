from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, func
from sqlalchemy.orm import relationship

from models.base import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=False)
    credits_status = Column(String(32), default="no_credits", nullable=False)
    usage_left = Column(Integer, default=0, nullable=True)
    usage_count = Column(Integer, default=0)
    acquisition_source = Column(String(128), nullable=True, index=True)
    acquisition_recorded_at = Column(DateTime, nullable=True)
    last_screen_key = Column(String(64), nullable=True, index=True)
    last_screen_at = Column(DateTime, nullable=True)
    last_request_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    designs = relationship("Design", back_populates="user")
