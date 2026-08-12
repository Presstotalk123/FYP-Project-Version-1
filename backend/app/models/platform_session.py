from sqlalchemy import Column, Integer, Date, DateTime, ForeignKey, Index
from sqlalchemy.sql import func
from app.database import Base


class PlatformSession(Base):
    """One row per student *login* — the unit of platform-time tracking.

    A student's time on the platform for a calendar day is the SUM of the
    durations of that day's sessions, where a session's duration is
    ``last_action_at - login_at``. Because the access token expires after
    ``ACCESS_TOKEN_EXPIRE_MINUTES`` (30), a returning student re-logs in and a
    *new* row is created — earlier sessions are never overwritten, and summing
    them gives the day's total (see ``app.services.platform_usage``).

    This is deliberately session-grained, unlike ``login_activities`` (one row
    per calendar day, used for the login-streak/calendar feature), which stays
    as-is.

    ``login_date`` is the student's login date in Singapore time (see
    ``app.core.time``) so daily grouping matches the civil calendar; the two
    timestamps are stored in UTC like the rest of the codebase.

    The row ``id`` is embedded in the JWT as the ``sid`` claim so each
    authenticated action can update its own session's ``last_action_at``.
    """
    __tablename__ = "platform_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    login_date = Column(Date, nullable=False)
    login_at = Column(DateTime(timezone=True), nullable=False)
    last_action_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_platform_sessions_user_date", "user_id", "login_date"),
    )
