from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.time import sgt_today
from app.database import get_db
from app.dependencies import get_current_sid, get_current_user, require_staff_role
from app.models.user import User
from app.schemas.login_activity import (
    LoginActivitySummary,
    OnlineSummary,
    OnlineUser,
    StudentUsageRow,
    UsageSummary,
)
from app.services import login_activity as login_activity_service
from app.services import platform_usage

router = APIRouter(prefix="/login-activity", tags=["login-activity"])


def _resolve_year_month(year: int | None, month: int | None) -> tuple[int, int]:
    today = sgt_today()
    return (year if year is not None else today.year, month if month is not None else today.month)


@router.get("", response_model=LoginActivitySummary)
def get_login_activity(
    year: int | None = Query(None, description="Calendar year (SGT); defaults to current"),
    month: int | None = Query(None, ge=1, le=12, description="Calendar month 1-12 (SGT); defaults to current"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current login streak plus this (or a requested) month's active login days.

    The streak is global and always computed against today (SGT). ``active_dates``
    covers only the requested month so the calendar can lazily fetch per month.
    """
    today = sgt_today()
    y = year if year is not None else today.year
    m = month if month is not None else today.month

    return LoginActivitySummary(
        current_streak=login_activity_service.current_streak(db, current_user.id),
        year=y,
        month=m,
        active_dates=login_activity_service.get_active_dates(db, current_user.id, y, m),
    )


@router.post("/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
def record_heartbeat(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sid: int | None = Depends(get_current_sid),
):
    """Advance the caller's current platform session's ``last_action_at``.

    Called (throttled) by the frontend on meaningful actions, and by the idle-tab
    timer in ``usePresenceHeartbeat``. Applies to every role — staff sessions are
    what let the /admin active-user count show a role split. Never fails the
    request (the service swallows its own errors).
    """
    platform_usage.touch_session(db, current_user, sid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/usage", response_model=UsageSummary)
def get_my_usage(
    year: int | None = Query(None, description="Calendar year (SGT); defaults to current"),
    month: int | None = Query(None, ge=1, le=12, description="Calendar month 1-12 (SGT); defaults to current"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The caller's own daily platform-time usage for a month (self-serve)."""
    y, m = _resolve_year_month(year, month)
    return platform_usage.usage_summary(db, current_user.id, y, m)


@router.get("/students/{student_id}/usage", response_model=UsageSummary)
def get_student_usage(
    student_id: int,
    year: int | None = Query(None, description="Calendar year (SGT); defaults to current"),
    month: int | None = Query(None, ge=1, le=12, description="Calendar month 1-12 (SGT); defaults to current"),
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """A given student's daily usage for a month. Staff/admin only."""
    y, m = _resolve_year_month(year, month)
    return platform_usage.usage_summary(db, student_id, y, m)


@router.get("/usage-overview", response_model=list[StudentUsageRow])
def get_usage_overview(
    year: int | None = Query(None, description="Calendar year (SGT); defaults to current"),
    month: int | None = Query(None, ge=1, le=12, description="Calendar month 1-12 (SGT); defaults to current"),
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """Per-student platform-time totals for a month, for the staff roster."""
    y, m = _resolve_year_month(year, month)
    return platform_usage.usage_overview(db, y, m)


@router.post("/leave", status_code=status.HTTP_204_NO_CONTENT)
def record_leave(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    sid: int | None = Depends(get_current_sid),
):
    """Mark the caller's session as gone so the active-user count drops them at once.

    Sent by the browser when a tab is hidden or unloaded. Only stamps ``left_at``;
    the session's recorded usage duration is untouched.
    """
    platform_usage.mark_left(db, current_user, sid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/online-summary", response_model=OnlineSummary)
def get_online_summary(
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """How many people are on the platform right now, split by role. Staff/admin only."""
    return platform_usage.count_online(db)


@router.get("/online", response_model=list[OnlineUser])
def get_online(
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """Who is on the platform right now, most recently seen first. Staff/admin only."""
    return platform_usage.list_online(db)
