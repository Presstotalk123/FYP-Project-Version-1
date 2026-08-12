from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class LoginActivity(Base):
    """One row per student per calendar day on which they logged in.

    ``login_date`` is the student's login date in Singapore time (see
    ``app.core.time``), not UTC — the streak and calendar are civil-calendar
    features. The unique constraint on ``(user_id, login_date)`` is the source of
    truth for "one active day per calendar day": duplicate same-day logins are
    rejected at the DB level and silently ignored by the recording code.
    """
    __tablename__ = "login_activities"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    login_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'login_date', name='_user_login_date_uc'),
    )
