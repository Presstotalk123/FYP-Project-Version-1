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

from sqlalchemy import func, or_, update
from sqlalchemy.orm import Session

from app.config import settings
from app.core.time import sgt_today
from app.models.platform_session import PlatformSession
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

# Minimum gap between successive ``last_action_at`` writes for one session. The
# frontend also throttles its heartbeat; this is the server-side backstop so a
# burst of actions costs at most one write per window (and bounds tracking
# granularity to ~this many seconds).
THROTTLE_SECONDS = 120


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def start_session(db: Session, user: User) -> int | None:
    """Open a new platform session at login; return its id (the JWT ``sid``).

    Covers every role: staff and admin sessions are what let the active-user
    count on /admin show a students-vs-staff split. Returns ``None`` on any
    failure — the caller still issues the token.
    """
    try:
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
    """Advance ``last_action_at`` for the caller's current session (throttled).

    ``sid`` is the session id from the JWT. When it is missing (a legacy token
    issued before this feature, or a dev-login token) we fall back to the user's
    latest session for today, creating one if none exists. Never raises.
    """
    try:
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
                # The throttle must not block un-setting left_at, or a user who
                # left and returned inside the 60s window would stay counted as
                # gone. The extra write only ever fires on a return.
                or_(
                    PlatformSession.last_action_at < threshold,
                    PlatformSession.left_at.isnot(None),
                ),
            )
            .values(last_action_at=now, left_at=None)
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except Exception:  # noqa: BLE001 - an action must succeed even if tracking fails
        db.rollback()
        logger.exception("Failed to touch platform session sid=%s user_id=%s", sid, getattr(user, "id", None))


def mark_left(db: Session, user: User, sid: int | None) -> None:
    """Record that the user's tab went away, so presence drops them at once.

    Sets ``left_at`` only — never ``last_action_at``, because a session's usage
    duration is ``last_action_at - login_at`` and moving it backwards would
    silently shorten the recorded platform time. Never raises.
    """
    try:
        if sid is None:
            return

        db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.id == sid,
                PlatformSession.user_id == user.id,
            )
            .values(left_at=_utc_now())
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except Exception:  # noqa: BLE001 - leaving must never fail the request
        db.rollback()
        logger.exception(
            "Failed to mark platform session left sid=%s user_id=%s", sid, getattr(user, "id", None)
        )


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


def _duration_seconds_between(login_at: datetime, last_action_at: datetime) -> int:
    """Non-negative whole-second duration between a session's two timestamps."""
    delta = (last_action_at - login_at).total_seconds()
    return int(delta) if delta > 0 else 0


def _duration_seconds(session: PlatformSession) -> int:
    """Non-negative whole-second duration of one session."""
    return _duration_seconds_between(session.login_at, session.last_action_at)


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
    """A student's ``daily_usage`` plus the month total and the all-time total,
    shaped for ``UsageSummary``."""
    days = daily_usage(db, user_id, year, month)
    all_time_seconds, all_time_active_days = lifetime_total(db, user_id)
    return {
        "year": year,
        "month": month,
        "total_seconds": sum(d["total_seconds"] for d in days),
        "all_time_seconds": all_time_seconds,
        "all_time_active_days": all_time_active_days,
        "days": days,
    }


def usage_overview(db: Session, year: int, month: int) -> list[dict]:
    """Per-student totals for the staff roster: this month AND all-time.

    One row per student who has *ever* had a session (so the all-time total is
    always visible, even in a month with no activity). Each row carries the
    selected month's figures (``total_seconds``, ``active_days``) and the
    cumulative figures across every day (``all_time_seconds``,
    ``all_time_active_days``). Sorted by all-time total descending.

    The all-time total is an exact live sum over every session ever recorded, so
    this necessarily reads the full session history for every student — there is
    no month-range filter that can bound that half of the work away, and it grows
    with the school year. What *is* avoidable is doing it wastefully: the previous
    version joined in the full ``User`` row and re-hydrated it once per session
    (a student with 300 sessions transferred and rebuilt their name/email/
    class_group 300 times). This fetches each student's identity once, then pulls
    only the four session columns actually used, via ``user_id IN (...)`` (hits
    the ``user_id`` index) instead of a per-row join. Duration is still summed in
    Python rather than in SQL, matching ``daily_usage``'s reasoning: SQLite and
    Postgres don't agree on datetime-subtraction semantics, so keeping the
    arithmetic in Python keeps this function's output identical on both.

    If the full-history scan itself ever becomes the bottleneck (as opposed to
    just the per-row overhead fixed here), the real structural fix is a
    maintained per-student rollup updated incrementally in ``touch_session``,
    so a read no longer has to replay the entire session history.
    """
    first, last = _month_bounds(year, month)

    students = (
        db.query(User.id, User.name, User.email, User.class_group)
        .filter(User.role == UserRole.STUDENT)
        .all()
    )
    if not students:
        return []
    student_info = {s.id: s for s in students}

    session_rows = (
        db.query(
            PlatformSession.user_id,
            PlatformSession.login_date,
            PlatformSession.login_at,
            PlatformSession.last_action_at,
        )
        .filter(PlatformSession.user_id.in_(student_info.keys()))
        .all()
    )

    totals: dict[int, dict] = {}
    month_days: dict[int, set[date]] = defaultdict(set)
    all_days: dict[int, set[date]] = defaultdict(set)
    for user_id, login_date, login_at, last_action_at in session_rows:
        acc = totals.get(user_id)
        if acc is None:
            info = student_info[user_id]
            acc = totals[user_id] = {
                "student_id": info.id,
                "name": info.name,
                "email": info.email,
                "class_group": info.class_group,
                "total_seconds": 0,
                "all_time_seconds": 0,
            }
        duration = _duration_seconds_between(login_at, last_action_at)
        acc["all_time_seconds"] += duration
        all_days[user_id].add(login_date)
        if first <= login_date <= last:
            acc["total_seconds"] += duration
            month_days[user_id].add(login_date)

    result = []
    for uid, acc in totals.items():
        acc["active_days"] = len(month_days[uid])
        acc["all_time_active_days"] = len(all_days[uid])
        result.append(acc)
    result.sort(key=lambda r: r["all_time_seconds"], reverse=True)
    return result


def lifetime_total(db: Session, user_id: int) -> tuple[int, int]:
    """A student's all-time platform time: ``(total_seconds, active_days)`` across
    every session ever, regardless of month."""
    sessions = (
        db.query(PlatformSession)
        .filter(PlatformSession.user_id == user_id)
        .all()
    )
    total = sum(_duration_seconds(s) for s in sessions)
    days = len({s.login_date for s in sessions})
    return total, days


def _presence_cutoff() -> datetime:
    """Actions older than this no longer count as being online."""
    return _utc_now() - timedelta(seconds=settings.PRESENCE_WINDOW_SECONDS)


def _online_filters():
    """Rows for users who are currently on the platform.

    A session counts when its last action is inside the presence window and it
    has not been marked left since that action (a user who left and came back
    has ``left_at`` cleared by ``touch_session``).
    """
    return (
        PlatformSession.last_action_at > _presence_cutoff(),
        or_(
            PlatformSession.left_at.is_(None),
            PlatformSession.left_at <= PlatformSession.last_action_at,
        ),
        User.is_active == 1,
    )


def count_online(db: Session) -> dict:
    """How many distinct users are online right now, split by role.

    DISTINCT because a user accumulates one ``platform_sessions`` row per login,
    so an active day leaves several behind.
    """
    rows = (
        db.query(User.role, func.count(func.distinct(PlatformSession.user_id)))
        .join(PlatformSession, PlatformSession.user_id == User.id)
        .filter(*_online_filters())
        .group_by(User.role)
        .all()
    )

    by_role: dict[str, int] = {}
    for role, n in rows:
        # SQLAlchemy may hand back the enum or the raw string depending on backend.
        key = role.value if isinstance(role, UserRole) else str(role)
        by_role[key] = by_role.get(key, 0) + int(n)

    students = by_role.get("student", 0)
    staff = by_role.get("staff", 0) + by_role.get("admin", 0)
    return {"total": students + staff, "students": students, "staff": staff}


def list_online(db: Session) -> list[dict]:
    """Who is online right now, most recently seen first."""
    now = _utc_now()
    rows = (
        db.query(
            User.id,
            User.name,
            User.email,
            User.role,
            User.class_group,
            func.max(PlatformSession.last_action_at).label("seen_at"),
        )
        .join(PlatformSession, PlatformSession.user_id == User.id)
        .filter(*_online_filters())
        .group_by(User.id, User.name, User.email, User.role, User.class_group)
        .order_by(func.max(PlatformSession.last_action_at).desc())
        .all()
    )

    out: list[dict] = []
    for uid, name, email, role, class_group, seen_at in rows:
        # SQLite reads DateTime(timezone=True) back naive; the stored value is UTC.
        if seen_at is not None and seen_at.tzinfo is None:
            seen_at = seen_at.replace(tzinfo=timezone.utc)
        out.append({
            "id": uid,
            "name": name,
            "email": email,
            "role": role.value if isinstance(role, UserRole) else str(role),
            "class_group": class_group,
            "seconds_ago": max(0, int((now - seen_at).total_seconds())) if seen_at else 0,
        })
    return out
