from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class RABagheeraMessage(Base):
    """One message between a student and Bagheera (the AI tutor) on an RA question.

    A student has one conversation per question (all its parts): the chat, and the
    "Explain my mistake" replies, which are tied to the attempt they explain (one each).
    Bagheera never grades; the grader stays the deterministic prover. A reply that gave
    the answer away is replaced before it is shown (services/ra/bagheera.py): ``guarded``
    is then 1 and ``blocked_content`` keeps what was held back, for staff only.
    """
    __tablename__ = "ra_bagheera_messages"
    __table_args__ = (
        Index("ix_ra_bagheera_user_question", "user_id", "question_id", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("ra_questions.id"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("ra_question_parts.id"), nullable=True)
    kind = Column(String(10), nullable=False, default="chat")          # chat | explain
    role = Column(String(10), nullable=False)                           # user | assistant
    content = Column(Text, nullable=False)
    attempt_id = Column(Integer, ForeignKey("ra_attempts.id"), nullable=True, index=True)   # explain only
    guarded = Column(Integer, nullable=False, default=0)
    blocked_content = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
