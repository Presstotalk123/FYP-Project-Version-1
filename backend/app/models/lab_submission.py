from sqlalchemy import Column, Integer, Text, Float, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class LabSubmission(Base):
    """One normalized graded attempt for any lab item kind."""
    __tablename__ = "lab_submissions"
    __table_args__ = (
        Index("ix_lab_submissions_lab_user", "lab_id", "user_id"),
        Index("ix_lab_submissions_item", "lab_item_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False, index=True)
    lab_item_id = Column(Integer, ForeignKey("lab_items.id"), nullable=False, index=True)
    lab_task_id = Column(Integer, nullable=True)  # sqllab-question task id (no FK; cross-table reference)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("lab_sessions.id"), nullable=False)

    is_passed = Column(Integer, nullable=False, default=0)
    score_earned = Column(Float, nullable=True)
    score_total = Column(Float, nullable=True)
    detail_json = Column(Text, nullable=True)

    # Staff override (AI-graded items)
    override_score_earned = Column(Float, nullable=True)
    override_score_total = Column(Float, nullable=True)
    override_reason = Column(Text, nullable=True)
    overridden_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    overridden_at = Column(DateTime(timezone=True), nullable=True)

    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
