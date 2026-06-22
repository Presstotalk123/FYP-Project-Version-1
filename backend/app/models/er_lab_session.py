from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.sql import func
from app.database import Base


class ErLabSession(Base):
    __tablename__ = "er_lab_sessions"
    __table_args__ = (
        Index("ix_er_lab_sessions_lab_user", "er_lab_id", "user_id"),
        Index("ix_er_lab_sessions_lab_active", "er_lab_id", "is_active"),
        Index(
            "uq_active_er_session_per_user_lab",
            "er_lab_id", "user_id",
            unique=True,
            postgresql_where=text("is_active = 1"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    er_lab_id = Column(Integer, ForeignKey("er_labs.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    is_active = Column(Integer, default=1)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
