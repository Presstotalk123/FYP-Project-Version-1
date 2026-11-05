"""Normalization content and immutable submissions, independent of SQL and ERD."""
from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class NormalizationQuestion(Base):
    __tablename__ = "normalization_questions"

    id = Column(Integer, primary_key=True)
    source_slug = Column(String(100), unique=True, nullable=True)
    title = Column(String(255), nullable=False)
    difficulty = Column(String(16), nullable=False)
    scenario = Column(Text, nullable=False)
    relation_name = Column(String(100), nullable=False)
    attributes = Column(JSON, nullable=False)
    statements = Column(JSON, nullable=False)
    sample_rows = Column(JSON, nullable=False)
    target_normal_form = Column(String(8), nullable=False)
    approved_fds = Column(JSON, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    semantic_judge_enabled = Column(Integer, nullable=False, default=0)
    hide_correctness = Column(Integer, nullable=False, default=0)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_published = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Integer, nullable=False, default=0)
    owner_assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class NormalizationSubmission(Base):
    __tablename__ = "normalization_submissions"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_normalization_request"),
        Index("ix_normalization_question_user", "question_id", "user_id", "created_at"),
    )

    id = Column(String(36), primary_key=True)
    request_key = Column(String(36), nullable=False)
    question_id = Column(Integer, ForeignKey("normalization_questions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    question_version = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="processing")
    original_result = Column(JSON, nullable=True)
    semantic_evidence = Column(JSON, nullable=True)
    fd_percent = Column(Integer, nullable=True)
    normalization_percent = Column(Integer, nullable=True)
    overall_percent = Column(Integer, nullable=True)
    decision = Column(String(24), nullable=True)
    review_version = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class NormalizationReview(Base):
    __tablename__ = "normalization_reviews"

    id = Column(Integer, primary_key=True)
    submission_id = Column(String(36), ForeignKey("normalization_submissions.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    decision = Column(String(24), nullable=False)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
