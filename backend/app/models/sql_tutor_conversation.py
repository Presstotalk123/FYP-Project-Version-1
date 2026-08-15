from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401
from app.models import question as _question  # noqa: F401
from app.models import lab_task as _lab_task  # noqa: F401
from app.models import sql_concept as _sql_concept  # noqa: F401


class SqlTutorConversation(Base):
    """Adaptive SQL-tutor conversation state (the ``SQL_TUTOR_ADAPTIVE`` path).

    Runs alongside the legacy ``tutor_chat_conversations`` during rollout, gated by
    the engine flag, mirroring how ``erd_tutor_conversations`` runs alongside the
    Dify path. Carries the per-conversation scaffolding state the chatbot reads at
    the start of every turn. Scaffolding is tracked against ``active_concept_id`` so
    a student can be independent on one concept while needing full support on another.
    """
    __tablename__ = "sql_tutor_conversations"
    __table_args__ = (
        Index("ix_sql_tutor_conv_user_question", "user_id", "question_id"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    lab_task_id = Column(Integer, ForeignKey("lab_tasks.id"), nullable=True)
    context_type = Column(String(20), nullable=False, default="question")  # question | lab | course
    # full | guided | minimal | independent
    scaffolding_level = Column(String(20), nullable=False, default="full")
    active_concept_id = Column(Integer, ForeignKey("sql_concepts.id"), nullable=True)
    last_solo_level = Column(String(24), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
