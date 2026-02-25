from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class LabSession(Base):
    """Model for tracking active student lab sessions"""
    __tablename__ = "lab_sessions"

    id = Column(Integer, primary_key=True, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Student's isolated database copy
    db_file_path = Column(String(500), nullable=False)  # e.g., "lab_1_student_42.db"

    # Session state
    is_active = Column(Integer, default=1)  # 1=active, 0=terminated

    # Timestamps
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    # Composite indexes for faster lookups
    __table_args__ = (
        Index('idx_lab_user', 'lab_id', 'user_id'),
        Index('idx_active_sessions', 'lab_id', 'is_active'),
    )
