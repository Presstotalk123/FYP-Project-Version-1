from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class LabTask(Base):
    """Model for lab tasks with hashed correct answers"""
    __tablename__ = "lab_tasks"

    id = Column(Integer, primary_key=True, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False, index=True)

    # Task content
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # Answer validation (nullable - can be assigned later)
    correct_answer_hash = Column(String(64), nullable=True)  # SHA256
    correct_query = Column(Text, nullable=True)  # Reference query

    # Ordering
    order_index = Column(Integer, nullable=False, default=0)

    # Metadata
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Soft delete
    is_deleted = Column(Integer, default=0)

    # Composite indexes
    __table_args__ = (
        Index('idx_lab_order', 'lab_id', 'order_index'),
        Index('idx_lab_created', 'lab_id', 'created_at'),
    )
