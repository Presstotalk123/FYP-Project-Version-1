from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base
from app.models.question import difficulty_db_type  # shared easy|medium|hard enum


class SqlLabQuestion(Base):
    """A pool question with a seed DB + ordered tasks, solved on a writable copy."""
    __tablename__ = "sql_lab_questions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    difficulty = Column(difficulty_db_type(), nullable=False)
    status = Column(String(16), nullable=False, server_default="draft")  # 'draft' | 'ready'

    schema_sql = Column(Text, nullable=False)
    sample_data_sql = Column(Text, nullable=False)
    template_db_path = Column(String(500), nullable=True)  # set on create

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Integer, default=0)


class SqlLabTask(Base):
    """One ordered task within a SqlLabQuestion."""
    __tablename__ = "sql_lab_tasks"
    __table_args__ = (
        Index("idx_sqllab_q_order", "sql_lab_question_id", "order_index"),
    )

    id = Column(Integer, primary_key=True, index=True)
    sql_lab_question_id = Column(Integer, ForeignKey("sql_lab_questions.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)            # the prompt
    order_index = Column(Integer, nullable=False, default=0)
    correct_query = Column(Text, nullable=True)
    correct_answer_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_deleted = Column(Integer, default=0)
