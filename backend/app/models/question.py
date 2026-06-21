from sqlalchemy import Column, Integer, String, Text, DateTime, Enum as SQLEnum, ForeignKey
from sqlalchemy.sql import func
from app.database import Base
import enum


class Difficulty(str, enum.Enum):
    """Question difficulty levels"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


def difficulty_db_type() -> SQLEnum:
    """SQLAlchemy type for the shared ``difficulty`` enum column.

    Persists the lowercase enum *values* (``easy``/``medium``/``hard``) to match
    the Postgres ``difficulty`` enum type. SQLAlchemy's default for a Python enum
    is to persist the member *name* (``EASY``/``MEDIUM``/``HARD``), which Postgres
    rejects ("invalid input value for enum difficulty"). SQLite does not enforce
    enum labels, so the mismatch only surfaces on Postgres/Supabase.

    Used by every difficulty column (questions, sql_lab_questions,
    graph_questions) so they stay in lockstep. See tests/test_difficulty_enum.py.
    """
    return SQLEnum(
        Difficulty,
        name="difficulty",
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class Question(Base):
    """Question model for SQL practice questions"""
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    difficulty = Column(difficulty_db_type(), nullable=False)

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
