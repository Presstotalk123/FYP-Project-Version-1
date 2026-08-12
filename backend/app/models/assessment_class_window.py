from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index
from app.database import Base


class AssessmentClassWindow(Base):
    """Per-class-group access window for an assessment (the Timing Gateway).

    One row per (assessment, class_group). When the owning assessment has
    ``gateway_enabled = 1``, a student may only join/access the assessment while
    the current server time is within ``[start_at, end_at)`` of the window matching
    their ``User.class_group``. ``end_at`` is also stamped onto the session as its
    immovable ``hard_deadline`` at join, so the effective deadline is the earlier of
    the personal timer and this window end. All timestamps are UTC.
    """

    __tablename__ = "assessment_class_windows"
    __table_args__ = (
        UniqueConstraint("assessment_id", "class_group", name="uq_assessment_class_window"),
        Index("ix_assessment_class_windows_assessment", "assessment_id", "class_group"),
    )

    id            = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    # Free-text class/tutorial group, matching User.class_group (there is no ClassGroup entity).
    class_group   = Column(String(100), nullable=False)
    # Window bounds in UTC. Access is allowed for start_at <= now < end_at.
    start_at      = Column(DateTime(timezone=True), nullable=False)
    end_at        = Column(DateTime(timezone=True), nullable=False)
    # 1 = this group's window participates in gating; 0 = configured but paused.
    is_enabled    = Column(Integer, default=1, nullable=False)
