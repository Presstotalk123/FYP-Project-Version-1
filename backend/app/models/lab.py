from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class Lab(Base):
    """Lab model for database lab classroom sessions"""
    __tablename__ = "labs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # Lab states - TWO INDEPENDENT flags
    is_published = Column(Integer, default=0)  # Visibility: 0=unpublished, 1=published
    is_running = Column(Integer, default=0)    # Active session: 0=stopped, 1=running

    # When set, students submitting task answers are not told whether they were
    # correct or incorrect - they just get a generic "submitted successfully" notice.
    hide_correctness = Column(Integer, default=0)

    # When set, the AI Tutor tab and the AI query-review hint are turned off for
    # students - independent of hide_correctness (correctness feedback stays as-is).
    disable_ai_assist = Column(Integer, default=0)

    # Template database
    template_db_path = Column(String(500), nullable=False)  # Filename of template DB

    # SQL/Cypher for recreating template (for editing)
    schema_sql = Column(Text, nullable=False)
    sample_data_sql = Column(Text, nullable=False)

    # Lab type: "sql" for SQL labs, "graph" for Cypher/graphqlite labs
    lab_type = Column(String(10), default="sql", nullable=False)

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Soft delete
    is_deleted = Column(Integer, default=0)

    # When set, this row is an assessment-owned clone (created at publish time) rather
    # than a master bank lab. Clones are excluded from bank listings/pickers and give
    # each published assessment its own isolated progress/attempt history.
    owner_assessment_id = Column(Integer, ForeignKey("assessments.id"), nullable=True, index=True)
