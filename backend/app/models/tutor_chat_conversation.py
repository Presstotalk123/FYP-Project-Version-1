from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401
from app.models import question as _question  # noqa: F401
from app.models import lab as _lab  # noqa: F401
from app.models import lab_session as _lab_session  # noqa: F401


class TutorChatConversation(Base):
    """One SQL-tutor conversation per (user, context).

    - context_type="question": keyed by (user_id, question_id).
    - context_type="lab":      keyed by (user_id, session_id) — labs are worked
      through a session, so the transcript ties to that student's run of the lab.
    """
    __tablename__ = "tutor_chat_conversations"
    __table_args__ = (
        Index("ix_tutor_chat_conv_lookup", "user_id", "context_type", "question_id", "session_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    context_type = Column(String(20), nullable=False)  # "question" | "lab"
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=True)
    session_id = Column(Integer, ForeignKey("lab_sessions.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
