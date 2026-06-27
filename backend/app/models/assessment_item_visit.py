from sqlalchemy import Column, Integer, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class AssessmentItemVisit(Base):
    __tablename__ = "assessment_item_visits"
    __table_args__ = (
        Index("ix_aiv_session_item", "session_id", "assessment_item_id", unique=True),
    )

    id                 = Column(Integer, primary_key=True, index=True)
    session_id         = Column(Integer, ForeignKey("assessment_sessions.id"), nullable=False)
    assessment_item_id = Column(Integer, ForeignKey("assessment_items.id"), nullable=False)
    first_visited_at   = Column(DateTime(timezone=True), server_default=func.now())
