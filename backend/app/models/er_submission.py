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

    # Staff score override. The columns above always hold the current truth, so
    # every reader — analytics aggregates, the student's mark — sees the corrected
    # score without knowing an override happened.
    #
    # The grader's own result is frozen here on the FIRST override and never
    # rewritten, so "what did the AI say" keeps one answer however many times a
    # score is later adjusted, and reverting can restore it exactly.
    original_grade_json = Column(Text, nullable=True)
    override_reason = Column(Text, nullable=True)
    overridden_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    overridden_at = Column(DateTime(timezone=True), nullable=True)

    # A staff member created this row from a diagram the student never submitted —
    # the assessment timer closes the session without submitting the open canvas, so
    # a saved draft with no grade is the normal shape of a lost attempt.
    #
    # Not the same event as the override above: an added row can be corrected later,
    # and both markers then apply. `added_by_staff_id IS NOT NULL` is the whole
    # definition of "staff added this", which the UI badge and analytics read.
    added_by_staff_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    added_reason = Column(Text, nullable=True)
