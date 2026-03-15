from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class LabTaskSubmission(Base):
    """Model for tracking student task submissions and progress"""
    __tablename__ = "lab_task_submissions"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("lab_tasks.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("lab_sessions.id"), nullable=False, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False, index=True)

    # Submission details
    submitted_query = Column(Text, nullable=False)
    submitted_result_hash = Column(String(64), nullable=False)  # SHA256 hash
    is_correct = Column(Integer, nullable=False)  # 0=incorrect, 1=correct

    # Execution metadata
    execution_time_ms = Column(Float, nullable=False)
    row_count = Column(Integer, default=0)

    # Timestamp
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Composite indexes for faster lookups
    __table_args__ = (
        Index('idx_task_user', 'task_id', 'user_id'),
        Index('idx_user_lab', 'user_id', 'lab_id'),
        Index('idx_task_submitted', 'task_id', 'submitted_at'),
    )
