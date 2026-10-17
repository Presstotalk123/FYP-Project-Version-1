from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class RAQuestion(Base):
    """A relational-algebra question (FYP RA module, see app/core/ra).

    Graded by app/core/ra/grader.py against ``model_answer``. The question may have no
    data at all (``data_sql`` empty), as the course tutorials don't: answers are then
    checked on test databases generated from the schema, built once when the question is
    saved and stored in ``suite_json`` so every student meets exactly the same ones.
    """
    __tablename__ = "ra_questions"
    __table_args__ = (
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_ra_questions_difficulty"),
        Index("ix_ra_questions_is_deleted", "is_deleted"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)              # markdown, shown to students
    difficulty = Column(String(10), nullable=False, default="medium")

    schema_sql = Column(Text, nullable=False)               # CREATE TABLE …; CHECK constraints = assumptions
    data_sql = Column(Text, nullable=False, default="")     # INSERT …; may be empty
    model_answer = Column(Text, nullable=False)             # RA, step by step; never shown to students
    # [{"statement": "R1" | null, "label": "the Civil Engineering courses"}]; NULL = every model step.
    checkpoints_json = Column(Text, nullable=True)

    # 0/1 flags, following the app's Integer-flag convention.
    # Students see the ✓/◐/○ comparison of their steps with the model's ("Show structure").
    show_step_direction = Column(Integer, nullable=False, default=1)
    # Compare results as bags (duplicates count) instead of sets.
    compare_bags = Column(Integer, nullable=False, default=0)
    # Students only learn "submitted", not whether it was correct (mirrors questions.hide_correctness).
    hide_correctness = Column(Integer, nullable=False, default=0)
    is_published = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Integer, nullable=False, default=0)

    # The generated test databases and the self-test report (core/ra/suite.py), rebuilt
    # whenever the schema, data or model answer changes.
    suite_json = Column(Text, nullable=True)
    suite_summary_json = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    # Set on an assessment-owned clone (created at publish time); clones stay out of the bank.
    owner_assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=True, index=True)
