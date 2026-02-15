from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class ERDiagramQuestion(Base):
    __tablename__ = "er_diagram_questions"

    id = Column(Integer, primary_key=True, index=True)
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
