from sqlalchemy import Column, Integer, Text, Float, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Attempt(Base):
    """Model for tracking student query attempts"""
    __tablename__ = "attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)

    # Query submitted by student
    query = Column(Text, nullable=False)

    # Validation result
    is_correct = Column(Integer, nullable=False)  # Using Integer for SQLite (0/1)

    # Execution details
    execution_time_ms = Column(Float)
    error_message = Column(Text)

    # Timestamp
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
