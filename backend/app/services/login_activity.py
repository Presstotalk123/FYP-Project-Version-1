"""Student login-activity tracking: record login days, compute the streak, and
list a month's active days.

A "day" here is a Singapore calendar day (see ``app.core.time``), not a UTC day
and not a 24-hour rolling window. All logic funnels through ``sgt_today()`` so the
day boundary is consistent everywhere.
"""

import calendar
import logging
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import sgt_today
from app.models.login_activity import LoginActivity
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)


def record_login_day(db: Session, user: User) -> None:
    """Record today's (SGT) login for a student, at most once per calendar day.

    Only students are tracked. The unique constraint on
    ``(user_id, login_date)`` guarantees a single row per student per day: we
    check first to avoid the common no-op write, and still catch IntegrityError
    so a race between two same-day logins can't surface an error.

    Login recording must never block issuing the token, so any unexpected failure
    is logged and swallowed — a missed streak day is far better than a failed login.
    """
    try:
        if user.role != UserRole.STUDENT:
            return

        today = sgt_today()
        exists = (
            db.query(LoginActivity.id)
            .filter(
                LoginActivity.user_id == user.id,
                LoginActivity.login_date == today,
            )
            .first()
        )
        if exists:
            return

        db.add(LoginActivity(user_id=user.id, login_date=today))
        db.commit()
    except IntegrityError:
        # Another concurrent login already recorded today — the constraint did its
        # job. Roll back so the session is usable and treat it as success.
        db.rollback()
    except Exception:  # noqa: BLE001 - login must succeed even if tracking fails
        db.rollback()
        logger.exception("Failed to record login day for user_id=%s", getattr(user, "id", None))


def _login_dates(db: Session, user_id: int) -> set[date]:
    """All distinct login dates for a user, as a set for O(1) membership tests."""
    rows = (
        db.query(LoginActivity.login_date)
        .filter(LoginActivity.user_id == user_id)
        .all()
    )
    return {row[0] for row in rows}


def current_streak(db: Session, user_id: int) -> int:
    """Number of consecutive calendar days (ending today, SGT) with a login.

    Rules:
    - A login today continues the streak from yesterday.
    - First login ever → 1.
    - Yesterday missed → streak resets to 1 (only today counts).
    - Multiple logins on one day count once (dates are a set / DB-unique).

    The walk is anchored at today, or yesterday as a fallback: normally today's
    login is already recorded by the time the dashboard loads, but if it somehow
    isn't (e.g. a stale view) a streak ending yesterday is still shown rather than 0.
    """
    dates = _login_dates(db, user_id)
    if not dates:
        return 0

    today = sgt_today()
    if today in dates:
        anchor = today
    elif (today - timedelta(days=1)) in dates:
        anchor = today - timedelta(days=1)
    else:
        return 0

    streak = 0
    day = anchor
    while day in dates:
        streak += 1
        day -= timedelta(days=1)
    return streak


def get_active_dates(db: Session, user_id: int, year: int, month: int) -> list[date]:
    """Login dates for the user within the given SGT year/month, ascending."""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    rows = (
        db.query(LoginActivity.login_date)
        .filter(
            LoginActivity.user_id == user_id,
            LoginActivity.login_date >= first,
            LoginActivity.login_date <= last,
        )
        .order_by(LoginActivity.login_date.asc())
        .all()
    )
    return [row[0] for row in rows]
