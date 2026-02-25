from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class LabAttempt(Base):
    """Model for tracking student lab query attempts"""
    __tablename__ = "lab_attempts"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("lab_sessions.id"), nullable=False, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Query details
    query = Column(Text, nullable=False)
    success = Column(Integer, nullable=False)  # 0=failed, 1=success
    execution_time_ms = Column(Float, nullable=False)
    row_count = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)

    # Timestamp
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Composite index for faster lookups
    __table_args__ = (
        Index('idx_session_submitted', 'session_id', 'submitted_at'),
        Index('idx_user_lab', 'user_id', 'lab_id'),
    )
