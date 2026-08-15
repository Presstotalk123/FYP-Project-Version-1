from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401
from app.models import question as _question  # noqa: F401
from app.models import lab_task as _lab_task  # noqa: F401
from app.models import sql_concept as _sql_concept  # noqa: F401


class LearningEvent(Base):
    """Centralized, append-only pedagogical telemetry.

    One row per granular learning event (query submitted, hint requested,
    metacognitive prompt shown, chat opened, scaffolding changed, SOLO classified,
    ...). A single polymorphic ``event_type`` column (rather than one table per
    event type) lets the Learner Profiling Agent scan all of a student's events
    chronologically in one query. This is the backbone the mastery, scaffolding,
    and SOLO subsystems derive from. Writes are gated by ``AKELA_AGENTS_ENABLED``.
    """
    __tablename__ = "learning_events"
    __table_args__ = (
        Index("ix_learning_events_user_time", "user_id", "created_at"),
        Index("ix_learning_events_type_time", "event_type", "created_at"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    event_type = Column(String(40), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    lab_task_id = Column(Integer, ForeignKey("lab_tasks.id"), nullable=True)
    concept_id = Column(Integer, ForeignKey("sql_concepts.id"), nullable=True)
    # Points at either tutor_chat_conversations.id or sql_tutor_conversations.id
    # depending on context; kept as a plain integer (no FK) since it is polymorphic.
    conversation_id = Column(Integer, nullable=True)
    payload_json = Column(Text, nullable=True)  # event-specific structured detail
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
