from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class UserProgress(Base):
    """Model for tracking user progress on questions"""
    __tablename__ = "user_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)

    # Progress tracking
    completed = Column(Integer, default=0)  # Using Integer for SQLite (0/1)
    attempts_count = Column(Integer, default=0)

    # Timestamps
    first_completed_at = Column(DateTime(timezone=True))
    last_attempted_at = Column(DateTime(timezone=True))

    # Ensure unique combination of user and question
    __table_args__ = (
        UniqueConstraint('user_id', 'question_id', name='_user_question_uc'),
    )
