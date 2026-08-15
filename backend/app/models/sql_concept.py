from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from app.database import Base


class SqlConcept(Base):
    """A single SQL concept in the learning taxonomy (e.g. ``inner_join``).

    The taxonomy is a small, hand-authored curriculum artifact seeded once from
    ``app.services.concept_taxonomy_seed`` (not LLM-generated). Concepts are the
    unit that mastery is tracked against and that the LAD dependency graph renders.
    """
    __tablename__ = "sql_concepts"
    __table_args__ = (
        Index("ix_sql_concepts_category", "category"),
    )
    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(64), nullable=False, unique=True, index=True)  # e.g. "inner_join"
    display_name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(40), nullable=False)  # filtering | joins | aggregation | ...
    is_active = Column(Integer, nullable=False, default=1)  # 0/1 for SQLite
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
