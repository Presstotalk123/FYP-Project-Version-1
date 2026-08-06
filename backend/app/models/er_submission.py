from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class ErSubmission(Base):
    """One row per graded ERD submission (LangGraph engine only).

    Written by the SSE persistence wrapper after the `done` event — inside the
    never-raise block, so analytics can never break a delivered grade. No ORM
    relationships (codebase convention: explicit joins).
    """

    __tablename__ = "er_submissions"
    __table_args__ = (
        # The analytics access patterns: a question's submissions (optionally one
        # student's) and a question's timeline.
        Index("ix_er_submissions_question_user", "er_diagram_question_id", "user_id"),
        Index("ix_er_submissions_question_created", "er_diagram_question_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    er_diagram_question_id = Column(
        Integer, ForeignKey("er_diagram_questions.id"), nullable=False, index=True
    )
    score_earned = Column(Float, nullable=True)
    score_total = Column(Float, nullable=True)
    score_percent = Column(Float, nullable=True)
    score_label = Column(String(20), nullable=True)
    checks_json = Column(Text, nullable=True)
    submitted_image_storage_key = Column(String(255), nullable=True)
    submitted_xml = Column(Text, nullable=True)
    submission_description = Column(Text, nullable=True)
    hint_level_at_submit = Column(Integer, nullable=True)
    ibl_stage_at_submit = Column(String(30), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
