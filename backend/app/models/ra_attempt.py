from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class RAAttempt(Base):
    """One graded submission of a relational-algebra answer (FYP RA module).

    Every submission is kept, correct or not, with the grader's full result so staff can
    see exactly what the student was shown. A staff override replaces the verdict for
    marking without touching the grader's original ``verdict``/``result_json``.
    """
    __tablename__ = "ra_attempts"
    __table_args__ = (
        Index("ix_ra_attempts_user_question", "user_id", "question_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("ra_questions.id"), nullable=False, index=True)
    answer = Column(Text, nullable=False)

    # correct | wrong_columns | wrong_result | wrong_in_general | invalid_expression
    verdict = Column(String(30), nullable=False)
    is_correct = Column(Integer, nullable=False, default=0)        # 0/1
    method = Column(String(10), nullable=True)                     # proof | tested | sample
    result_json = Column(Text, nullable=False)                     # GradeResult.to_dict()
    elapsed_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Staff override (dispute review): the corrected outcome, why, who, when.
    override_is_correct = Column(Integer, nullable=True)
    override_reason = Column(Text, nullable=True)
    overridden_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    overridden_at = Column(DateTime(timezone=True), nullable=True)
