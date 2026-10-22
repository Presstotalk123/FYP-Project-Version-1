from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class RAQuestionPart(Base):
    """One part of a relational-algebra question: (i), (ii), … on the question's schema.

    Every question has at least one part. A question with a single unlabelled part is an
    ordinary question; with several, students solve each part in turn on the same schema
    and data, and in an assessment each part earns its own ``marks``. Each part has its
    own model answer and therefore its own generated test databases (``suite_json``).

    Parts are soft-deleted (attempts point at them).
    """
    __tablename__ = "ra_question_parts"
    __table_args__ = (
        Index("ix_ra_question_parts_question", "question_id", "is_deleted", "position"),
    )

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("ra_questions.id"), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    label = Column(String(50), nullable=False, default="")      # e.g. "(i)"; "" for a single part
    description = Column(Text, nullable=False, default="")      # markdown, shown to students
    marks = Column(Integer, nullable=False, default=1)

    model_answer = Column(Text, nullable=False)                 # never shown to students
    # [{"statement": "R1" | null, "label": "…"}]; NULL = every model step (see ra_question.py).
    checkpoints_json = Column(Text, nullable=True)
    suite_json = Column(Text, nullable=True)
    suite_summary_json = Column(Text, nullable=True)

    is_deleted = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
