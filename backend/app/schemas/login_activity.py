from datetime import date
from typing import List

from pydantic import BaseModel, Field


class LoginActivitySummary(BaseModel):
    """Login-streak indicator plus the active login days for one calendar month.

    ``current_streak`` is global (consecutive SGT days ending today). ``active_dates``
    are only the login dates within the requested month, for the calendar highlight.
    """
    current_streak: int = Field(..., description="Consecutive calendar days (SGT) ending today with a login")
    year: int = Field(..., description="Year of the returned active_dates")
    month: int = Field(..., description="Month (1-12) of the returned active_dates")
    active_dates: List[date] = Field(..., description="Login dates within the requested month (ISO YYYY-MM-DD)")
