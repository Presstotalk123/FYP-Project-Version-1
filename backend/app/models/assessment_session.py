from sqlalchemy import Column, Integer, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"
    __table_args__ = (
        Index("ix_assessment_sessions_user_assessment", "assessment_id", "user_id"),
    )

    id            = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active     = Column(Integer, default=1)  # 1=ongoing, 0=submitted
    # 1 once the student has ended & submitted this assessment. Assessments are
    # single-attempt: a completed session blocks re-joining/retaking regardless of is_active.
    attempt_complete = Column(Integer, default=0, nullable=False)
    joined_at     = Column(DateTime(timezone=True), server_default=func.now())
    submitted_at  = Column(DateTime(timezone=True), nullable=True)
