from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func
from app.database import Base


class ErLabSubmission(Base):
    __tablename__ = "er_lab_submissions"
    __table_args__ = (
        Index("ix_er_lab_submissions_question_user", "er_lab_question_id", "user_id"),
        Index("ix_er_lab_submissions_user_lab", "user_id", "er_lab_id"),
        Index("ix_er_lab_submissions_question_time", "er_lab_question_id", "submitted_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    er_lab_question_id = Column(Integer, ForeignKey("er_lab_questions.id"), nullable=False, index=True)
    er_lab_id = Column(Integer, ForeignKey("er_labs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey("er_lab_sessions.id"), nullable=False, index=True)

    submitted_xml = Column(Text, nullable=True)
    submitted_image_storage_key = Column(String(500), nullable=True)

    auto_score_earned = Column(Float, nullable=False)
    auto_score_total = Column(Float, nullable=False)
    auto_score_percent = Column(Float, nullable=False)
    auto_score_label = Column(String(255), nullable=False)
    auto_checks_json = Column(Text, nullable=False)
    auto_graded_at = Column(DateTime(timezone=True), nullable=False)

    override_score_earned = Column(Float, nullable=True)
    override_score_total = Column(Float, nullable=True)
    override_score_percent = Column(Float, nullable=True)
    override_reason = Column(Text, nullable=True)
    overridden_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    overridden_at = Column(DateTime(timezone=True), nullable=True)

    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
