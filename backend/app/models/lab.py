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
    is_published = Column(Integer, default=0)
    is_running = Column(Integer, default=0)

    # Join gating (carried over from the ER lab)
    join_password_hash = Column(String(255), nullable=False)
    join_password_plain = Column(String(255), nullable=False)

    # Optional shared-DB section (null when the lab has no shared-DB section)
    template_db_path = Column(String(500), nullable=True)
    schema_sql = Column(Text, nullable=True)
    sample_data_sql = Column(Text, nullable=True)

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Soft delete
    is_deleted = Column(Integer, default=0)
