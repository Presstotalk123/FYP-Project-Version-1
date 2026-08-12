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
    # Deadline for this attempt = join time + assessment.time_limit_minutes, credited forward by
    # query execution time. NULL = untimed attempt. Backend source of truth for lazy expiration.
    end_time      = Column(DateTime(timezone=True), nullable=True)
    # Immovable Timing-Gateway cap = the student's class-group window end_at, stamped at join.
    # NULL when the gateway is off. The effective deadline is the earlier of end_time and
    # hard_deadline, so query-time credit (which only pushes end_time) can never extend past
    # the group's window end.
    hard_deadline = Column(DateTime(timezone=True), nullable=True)
