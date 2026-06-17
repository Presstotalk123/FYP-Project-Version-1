from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class LabItem(Base):
    """An ordered entry in a lab: a reference to a pool question, or the shared-DB section."""
    __tablename__ = "lab_items"
    __table_args__ = (
        Index("ix_lab_items_lab_order", "lab_id", "order_index"),
        Index("ix_lab_items_lab_deleted", "lab_id", "is_deleted"),
    )

    id = Column(Integer, primary_key=True, index=True)
    lab_id = Column(Integer, ForeignKey("labs.id"), nullable=False, index=True)
    kind = Column(String(32), nullable=False)          # 'sql' | 'erd' | 'sqllab'
    ref_id = Column(Integer, nullable=True)            # pool question id for sql/erd; null for sqllab
    order_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_deleted = Column(Integer, default=0)
