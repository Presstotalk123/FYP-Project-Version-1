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
    difficulty = Column(SQLEnum(Difficulty, values_callable=lambda obj: [e.value for e in obj]), nullable=False)

    # SQLite database file path
    db_file_path = Column(String(500), nullable=False)

    # Hash of the correct answer
    correct_answer_hash = Column(String(64), nullable=False)

    # Original answer query, retained so staff can review and edit it later.
    # Nullable for questions created before this field was introduced.
    correct_answer_query = Column(Text, nullable=True)

    # SQL statements for reference and editing
    schema_sql = Column(Text, nullable=False)
    sample_data_sql = Column(Text, nullable=False)

    # Advanced SQL Testing (triggers / complex DML grading via hidden test script + check query).
    # 0/1 flag, following the same Integer-flag convention as is_deleted.
    advanced_sql_testing = Column(Integer, nullable=False, default=0)
    # Hidden staff-authored statements, only meaningful when advanced_sql_testing=1.
    test_script = Column(Text, nullable=True)
    check_query = Column(Text, nullable=True)

    # When set, students are not told whether a submission was correct/incorrect —
    # they just get a generic "submitted successfully" result. Real correctness is
    # still persisted (Attempt/UserProgress) for staff grading. Mirrors labs.hide_correctness.
    # 0/1 flag, following the same Integer-flag convention as is_deleted.
    hide_correctness = Column(Integer, nullable=False, default=0)

    # When set, grading is row-order-sensitive: the student's rows must be in the
    # same order as the correct answer query (enforces an explicit ORDER BY).
    # When unset (default), row order is ignored during comparison.
    # 0/1 flag, following the same Integer-flag convention as is_deleted.
    order_sensitive = Column(Integer, nullable=False, default=0)

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Visibility flag: 0=draft (staff only), 1=published (visible to students).
    # 0/1 flag, following the same Integer-flag convention as is_deleted. Mirrors labs.is_published.
    is_published = Column(Integer, nullable=False, default=0)

    # Soft delete flag
    is_deleted = Column(Integer, default=0)  # Using Integer for SQLite compatibility

    # When set, this row is an assessment-owned clone (created at publish time) rather
    # than a master bank question. Clones are excluded from bank listings/pickers and
    # give each published assessment its own isolated progress/attempt history.
    owner_assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=True, index=True)

    # LeetCode problem number for questions imported from the LeetCode bank
    # (DATABASE_README_EN.md ordering). NULL for hand-authored / non-LeetCode questions.
    leetcode_id = Column(Integer, nullable=True, index=True)
