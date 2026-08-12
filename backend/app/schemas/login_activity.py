import datetime as _dt
from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class DailyUsage(BaseModel):
    """One calendar day's platform usage for a student.

    ``total_seconds`` is the SUM of that day's login sessions' durations (each
    session = ``last_action_at - login_at``), so multiple same-day logins add up.
    """
    # ``_dt.date`` (not the shadowed ``date`` name) so the field can be called ``date``.
    date: _dt.date = Field(..., description="Calendar day (SGT), ISO YYYY-MM-DD")
    total_seconds: int = Field(..., description="Sum of the day's session durations, in seconds")
    first_login_at: _dt.datetime = Field(..., description="Earliest login of the day (UTC)")
    last_action_at: _dt.datetime = Field(..., description="Latest recorded action of the day (UTC)")
    session_count: int = Field(..., description="Number of login sessions that day")


class UsageSummary(BaseModel):
    """A student's per-day usage for one calendar month, plus the month total."""
    year: int = Field(..., description="Year of the returned days")
    month: int = Field(..., description="Month (1-12) of the returned days")
    total_seconds: int = Field(..., description="Sum of total_seconds across the month's days")
    days: List[DailyUsage] = Field(..., description="Per-day usage, ascending by date")


class StudentUsageRow(BaseModel):
    """One student's month total, for the staff usage roster."""
    student_id: int
    name: Optional[str] = None
    email: str
    class_group: Optional[str] = None
    total_seconds: int = Field(..., description="Sum of the student's session durations this month")
    active_days: int = Field(..., description="Distinct calendar days with at least one session")


class LoginActivitySummary(BaseModel):
    """Login-streak indicator plus the active login days for one calendar month.

    ``current_streak`` is global (consecutive SGT days ending today). ``active_dates``
    are only the login dates within the requested month, for the calendar highlight.
    """
    current_streak: int = Field(..., description="Consecutive calendar days (SGT) ending today with a login")
    year: int = Field(..., description="Year of the returned active_dates")
    month: int = Field(..., description="Month (1-12) of the returned active_dates")
    active_dates: List[date] = Field(..., description="Login dates within the requested month (ISO YYYY-MM-DD)")
