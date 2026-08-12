from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.time import sgt_today
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.login_activity import LoginActivitySummary
from app.services import login_activity as login_activity_service

router = APIRouter(prefix="/login-activity", tags=["login-activity"])


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
