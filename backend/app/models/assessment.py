from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    is_published = Column(Integer, default=0)
    is_running = Column(Integer, default=0)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    is_deleted = Column(Integer, default=0)
    password = Column(String(255), nullable=True)
    # Optional time limit in whole minutes. NULL = untimed (assessment behaves as before).
    time_limit_minutes = Column(Integer, nullable=True)

    # Timing Gateway master toggle. 1 = access is driven by per-class-group windows
    # (see AssessmentClassWindow), superseding the manual is_running start/stop.
    gateway_enabled = Column(Integer, default=0, nullable=False)

    items = relationship(
        "AssessmentItem",
        back_populates="assessment",
        order_by="AssessmentItem.order_index",
        cascade="all, delete-orphan",
    )
