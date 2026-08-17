from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly,
# as the migration script does).
from app.models import user as _user  # noqa: F401
from app.models import er_diagram_question as _question  # noqa: F401


class ErDiagramDraft(Base):
    """A student's in-progress draw.io canvas for one ER question.

    One mutable row per (user, question), overwritten in place — not an audit
    record. What was actually graded lives in er_submissions.submitted_xml,
    which is append-only; mixing the two would put update churn on a table the
    analytics aggregates read.

    Exactly one index, the composite unique below: it is both the upsert target
    and the only lookup this feature performs, and every extra index is write
    cost on a table written every few seconds per active student.
    """

    __tablename__ = "er_diagram_drafts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "er_diagram_question_id", name="uq_er_draft_user_question"
        ),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    er_diagram_question_id = Column(
        Integer, ForeignKey("er_diagram_questions.id"), nullable=False
    )
    xml = Column(Text, nullable=False)
    # Bumped by the upsert, never read-modify-written. The client compares this
    # against the revision it last synced to decide whether another device has
    # moved ahead — a clock comparison would be wrong across machines.
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
