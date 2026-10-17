from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401
from app.models import sql_concept as _sql_concept  # noqa: F401


class ConceptMastery(Base):
    """A student's proficiency in one SQL concept.

    Written only by the Learner Profiling Agent (deterministic streak arithmetic);
    read by the adaptive chatbot and the LAD. ``mastery_level`` is a smooth 0..1
    value; the display band (novice/developing/proficient/mastered) is derived from
    it at read time. ``scaffolding_level`` is the per-concept AI-support level the
    tutor uses on every question tagged with this concept.
    """
    __tablename__ = "concept_mastery"
    __table_args__ = (
        Index("uq_concept_mastery_user_concept", "user_id", "concept_id", unique=True),
    )
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    concept_id = Column(Integer, ForeignKey("sql_concepts.id"), nullable=False, index=True)
    mastery_level = Column(Float, nullable=False, default=0.0)  # 0.0 .. 1.0
    consecutive_successes = Column(Integer, nullable=False, default=0)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    total_attempts = Column(Integer, nullable=False, default=0)
    # Adaptive scaffolding level for this concept: full | guided | minimal | independent.
    # NULL on rows that predate per-concept scaffolding; scaffolding_engine seeds it
    # from mastery_level on read and persists it on the next attempt.
    scaffolding_level = Column(String(20), nullable=True)
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
