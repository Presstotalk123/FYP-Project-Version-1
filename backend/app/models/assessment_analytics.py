from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Text, DateTime, ForeignKey, Index, text,
)
from sqlalchemy.sql import func
from app.database import Base


class AssessmentAnalytics(Base):
    """Materialized roster analytics for one assessment × class_group.

    One row per (assessment_id, class_group) — `class_group IS NULL` is the whole
    cohort. `payload` is the JSON-serialized `RosterAnalytics` (per-item/per-task
    breakdown + per-student weighted totals) so any report can read the shared result
    without recomputing. `version` is the `ASSESSMENT_ANALYTICS` cache-namespace
    generation at materialization time: a row whose version lags the current namespace
    version is stale and gets recomputed on next read (see
    assessment_scoring.get_or_compute_analytics).
    """
    __tablename__ = "assessment_analytics"
    # Two partial unique indexes (not a plain UNIQUE) so the cohort-wide row
    # (class_group IS NULL) is deduplicated on PostgreSQL, where NULLs are distinct.
    # Mirrors migrations/add_assessment_analytics_table.sql.
    __table_args__ = (
        Index(
            "uq_assessment_analytics_scope", "assessment_id", "class_group",
            unique=True,
            postgresql_where=text("class_group IS NOT NULL"),
            sqlite_where=text("class_group IS NOT NULL"),
        ),
        Index(
            "uq_assessment_analytics_cohort", "assessment_id",
            unique=True,
            postgresql_where=text("class_group IS NULL"),
            sqlite_where=text("class_group IS NULL"),
        ),
        Index("ix_assessment_analytics_assessment", "assessment_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=False)
    # NULL = cohort-wide; otherwise the class group this row aggregates.
    class_group = Column(String(255), nullable=True)
    student_count = Column(Integer, nullable=False, default=0)
    avg_weighted_score = Column(Float, nullable=True)
    payload = Column(Text, nullable=False)          # JSON-serialized RosterAnalytics
    version = Column(BigInteger, nullable=False, default=0)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
