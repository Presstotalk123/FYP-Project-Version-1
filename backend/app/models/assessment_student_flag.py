from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base

# Import the FK targets so their tables are registered on Base.metadata when
# this model is imported on its own (as the migration script does).
from app.models import user as _user  # noqa: F401
from app.models import assessment as _assessment  # noqa: F401


class AssessmentStudentFlag(Base):
    """One staff flag on one student for one assessment.

    Staff set the flag from the assessment student lists. The flag marks a
    student for attention and records why. A flag is a staff note, not
    attempt data: an attempt reset keeps it, and an assessment clone does
    not copy it. One row per (assessment, student): to set the flag again
    replaces the reason.
    """

    __tablename__ = "assessment_student_flags"
    __table_args__ = (
        UniqueConstraint("assessment_id", "user_id", name="uq_assessment_student_flag"),
    )

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    # Free text from staff. NULL when the flag has no reason.
    reason = Column(Text, nullable=True)
    # The staff user who set the flag, or who replaced it last.
    flagged_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
