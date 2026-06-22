from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func
from app.database import Base


class ErLabQuestion(Base):
    __tablename__ = "er_lab_questions"
    __table_args__ = (
        CheckConstraint("notation IN ('Chen')", name="ck_er_lab_questions_notation"),
        CheckConstraint(
            "difficulty_label IN ('Easy', 'Medium', 'Hard')",
            name="ck_er_lab_questions_difficulty",
        ),
        Index("ix_er_lab_questions_lab_order", "er_lab_id", "order_index"),
        Index("ix_er_lab_questions_lab_deleted", "er_lab_id", "is_deleted"),
    )

    id = Column(Integer, primary_key=True, index=True)
    er_lab_id = Column(Integer, ForeignKey("er_labs.id"), nullable=False, index=True)
    order_index = Column(Integer, nullable=False, default=0)

    title = Column(String(255), nullable=False)
    problem_statement = Column(Text, nullable=False)
    notation = Column(String(50), nullable=False, default="Chen")
    difficulty_label = Column(String(20), nullable=False)
    difficulty_rationale = Column(Text, nullable=False)
    rubric_md = Column(Text, nullable=False)
    rubric_json = Column(Text, nullable=False)
    instruction_history_json = Column(Text, nullable=False)

    model_answer_storage_key = Column(String(500), nullable=True)
    model_answer_url = Column(String(1000), nullable=True)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    is_deleted = Column(Integer, default=0)
