from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401


class SoloClassification(Base):
    """SOLO-taxonomy label for one student chat message.

    Produced asynchronously by the SOLO Classifier Agent. ``confidence`` is the
    model's self-reported confidence; when it falls below
    ``SOLO_CONFIDENCE_THRESHOLD`` the classification is not trusted to tailor the
    next reply (``used_fallback = 1``) and a generic Socratic prompt is used
    instead — the confidence-gating safeguard from the spec.
    """
    __tablename__ = "solo_classifications"
    __table_args__ = (
        Index("ix_solo_classifications_conv", "conversation_id", "created_at"),
        Index("ix_solo_classifications_user", "user_id", "created_at"),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # Polymorphic (sql_tutor_conversations.id); no FK to keep it context-agnostic.
    conversation_id = Column(Integer, nullable=True)
    message_id = Column(Integer, nullable=True)
    # prestructural | unistructural | multistructural | relational | extended_abstract
    solo_level = Column(String(24), nullable=False)
    confidence = Column(Float, nullable=False, default=0.0)
    used_fallback = Column(Integer, nullable=False, default=0)  # 0/1
    raw_model_output_json = Column(Text, nullable=True)  # audit trail
    created_at = Column(DateTime(timezone=True), server_default=func.now())
