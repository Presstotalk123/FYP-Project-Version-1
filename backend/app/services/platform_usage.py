"""Student platform-time tracking: open a session per login, advance its
``last_action_at`` on meaningful actions, and aggregate time per calendar day.

Model of "time spent" (see ``app.models.platform_session``): each login opens one
``platform_sessions`` row; a session's duration is ``last_action_at - login_at``;
a day's total is the SUM of that day's sessions. Days are Singapore calendar days
(``app.core.time``); timestamps are UTC.

Everything here is best-effort: tracking must never break a login or an
authenticated request, so writes are wrapped and failures are logged and swallowed
(a lost heartbeat is far better than a failed action).
"""

import calendar
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.time import sgt_today
from app.models.platform_session import PlatformSession
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# Minimum gap between successive ``last_action_at`` writes for one session. The
# frontend also throttles its heartbeat; this is the server-side backstop so a
# burst of actions costs at most one write per window (and bounds tracking
# granularity to ~this many seconds).
THROTTLE_SECONDS = 60


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def start_session(db: Session, user: User) -> int | None:
    """Open a new platform session for a student at login; return its id (the JWT
    ``sid``). Returns ``None`` for non-students or on any failure — the caller
    still issues the token.
    """
    try:
        if user.role != UserRole.STUDENT:
            return None

        now = _utc_now()
        session = PlatformSession(
            user_id=user.id,
            login_date=sgt_today(),
            login_at=now,
            last_action_at=now,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session.id
    except Exception:  # noqa: BLE001 - login must succeed even if tracking fails
        db.rollback()
        logger.exception("Failed to start platform session for user_id=%s", getattr(user, "id", None))
        return None


def touch_session(db: Session, user: User, sid: int | None) -> None:
    """Advance ``last_action_at`` for the student's current session (throttled).

    ``sid`` is the session id from the JWT. When it is missing (legacy token
    issued before this feature) we fall back to the student's latest session for
    today, creating one if none exists. Students only; never raises.
    """
    try:
        if user.role != UserRole.STUDENT:
            return

        if sid is None:
            today = sgt_today()
            latest = (
                db.query(PlatformSession.id)
                .filter(
                    PlatformSession.user_id == user.id,
                    PlatformSession.login_date == today,
                )
                .order_by(PlatformSession.id.desc())
                .first()
            )
            if latest is None:
                start_session(db, user)
                return
            sid = latest[0]

        now = _utc_now()
        threshold = now - timedelta(seconds=THROTTLE_SECONDS)
        # Single conditional UPDATE (no prior SELECT): writes at most once per
        # throttle window, and the user_id guard is defense-in-depth so a session
        # can only ever be advanced by its own owner.
        # synchronize_session=False: run the UPDATE directly in SQL without
        # evaluating the WHERE in Python against in-memory objects. Required for
        # SQLite dev, where DateTime(timezone=True) columns read back naive and
        # would raise "can't compare offset-naive and offset-aware" during the
        # default "evaluate" synchronization. We don't reuse these ORM instances
        # after the write, so no synchronization is needed.
        db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.id == sid,
                PlatformSession.user_id == user.id,
                PlatformSession.last_action_at < threshold,
            )
            .values(last_action_at=now)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except Exception:  # noqa: BLE001 - an action must succeed even if tracking fails
        db.rollback()
        logger.exception("Failed to touch platform session sid=%s user_id=%s", sid, getattr(user, "id", None))


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


def _sessions_in_month(db: Session, user_id: int, year: int, month: int) -> list[PlatformSession]:
    first, last = _month_bounds(year, month)
    return (
        db.query(PlatformSession)
        .filter(
            PlatformSession.user_id == user_id,
            PlatformSession.login_date >= first,
            PlatformSession.login_date <= last,
        )
        .order_by(PlatformSession.login_date.asc(), PlatformSession.login_at.asc())
        .all()
    )


def _duration_seconds(session: PlatformSession) -> int:
    """Non-negative whole-second duration of one session."""
    delta = (session.last_action_at - session.login_at).total_seconds()
    return int(delta) if delta > 0 else 0


def daily_usage(db: Session, user_id: int, year: int, month: int) -> list[dict]:
    """Per-day usage for one student in the given SGT month, ascending by date.

    Each entry: ``date``, ``total_seconds`` (Σ session durations), ``first_login_at``
    (earliest login), ``last_action_at`` (latest action), ``session_count``.
    Aggregation is done in Python so the same code works on SQLite and Postgres.
    """
    by_day: dict[date, list[PlatformSession]] = defaultdict(list)
    for s in _sessions_in_month(db, user_id, year, month):
        by_day[s.login_date].append(s)

    days: list[dict] = []
    for day in sorted(by_day):
        sessions = by_day[day]
        days.append(
            {
                "date": day,
                "total_seconds": sum(_duration_seconds(s) for s in sessions),
                "first_login_at": min(s.login_at for s in sessions),
                "last_action_at": max(s.last_action_at for s in sessions),
                "session_count": len(sessions),
            }
        )
    return days


def usage_summary(db: Session, user_id: int, year: int, month: int) -> dict:
    """A student's ``daily_usage`` plus the month total, shaped for ``UsageSummary``."""
    days = daily_usage(db, user_id, year, month)
    return {
        "year": year,
        "month": month,
        "total_seconds": sum(d["total_seconds"] for d in days),
        "days": days,
    }


def usage_overview(db: Session, year: int, month: int) -> list[dict]:
    """Per-student totals for the given SGT month, for the staff roster.

    One row per student who has any session that month: ``student_id``, ``name``,
    ``email``, ``class_group``, ``total_seconds`` (Σ over the month), ``active_days``
    (distinct login dates). Sorted by total time descending.
    """
    first, last = _month_bounds(year, month)
    rows = (
        db.query(PlatformSession, User)
        .join(User, User.id == PlatformSession.user_id)
        .filter(
            User.role == UserRole.STUDENT,
            PlatformSession.login_date >= first,
            PlatformSession.login_date <= last,
        )
        .all()
    )

    totals: dict[int, dict] = {}
    active_days: dict[int, set[date]] = defaultdict(set)
    for session, user in rows:
        acc = totals.get(user.id)
        if acc is None:
            acc = totals[user.id] = {
                "student_id": user.id,
                "name": user.name,
                "email": user.email,
                "class_group": user.class_group,
                "total_seconds": 0,
            }
        acc["total_seconds"] += _duration_seconds(session)
        active_days[user.id].add(session.login_date)

    result = []
    for uid, acc in totals.items():
        acc["active_days"] = len(active_days[uid])
        result.append(acc)
    result.sort(key=lambda r: r["total_seconds"], reverse=True)
    return result
