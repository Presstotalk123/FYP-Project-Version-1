from sqlalchemy import Column, Integer, String, Text, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import enum


class Difficulty(str, enum.Enum):
    """Question difficulty levels"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Question(Base):
    """Question model for SQL practice questions"""
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    difficulty = Column(SQLEnum(Difficulty), nullable=False)

    # SQLite database file path
    db_file_path = Column(String(500), nullable=False)

    # Hash of the correct answer
    correct_answer_hash = Column(String(64), nullable=False)

    # SQL statements for reference and editing
    schema_sql = Column(Text, nullable=False)
    sample_data_sql = Column(Text, nullable=False)

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Soft delete flag
    is_deleted = Column(Integer, default=0)  # Using Integer for SQLite compatibility
