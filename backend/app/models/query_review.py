from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401
from app.models import question as _question  # noqa: F401
from app.models import lab as _lab  # noqa: F401


class QueryReview(Base):
    """One persisted AI query-review (the auto-feedback a student gets on a query).

    The review is computed on the fly in the chatbot endpoints and returned to the
    browser; we also store it here so staff analytics can show a student's
    query-review history over time.

    - context_type="question": SQL practice question, keyed by (user_id, question_id).
    - context_type="lab":      lab task, carries lab_id/task_id/session_id.
    """
    __tablename__ = "query_reviews"
    __table_args__ = (
        Index("ix_query_review_question", "user_id", "context_type", "question_id"),
        Index("ix_query_review_lab", "user_id", "context_type", "lab_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    context_type = Column(String(20), nullable=False)  # "question" | "lab"
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=True)
    task_id = Column(Integer, nullable=True)
    session_id = Column(Integer, nullable=True)
    student_query = Column(Text, nullable=False)
    problem_token = Column(String(100), nullable=True)
    explanation = Column(Text, nullable=True)
    hint = Column(Text, nullable=True)
    db_state_issue = Column(String(100), nullable=True)   # labs only
    db_state_message = Column(Text, nullable=True)         # labs only
    created_at = Column(DateTime(timezone=True), server_default=func.now())
