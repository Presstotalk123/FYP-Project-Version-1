"""Application timezone helpers.

The platform stores all timestamps in UTC (see ``datetime.now(timezone.utc)``
throughout the codebase). Some features, however, need to reason about *calendar
days* in the application's local timezone — Singapore — rather than UTC days.
The login-streak feature is the first: "one active day per calendar day" and a
consecutive-day streak are only meaningful against a fixed civil calendar.

Singapore has never observed daylight saving time, so SGT is a fixed +08:00
offset. Using ``timezone(timedelta(hours=8))`` keeps this exact without pulling
in the IANA tz database (``tzdata``), which is not guaranteed to be present on
Windows dev machines.
"""

from datetime import date, datetime, timedelta, timezone

# Singapore Standard Time — a fixed +08:00 offset (no DST, ever).
SGT = timezone(timedelta(hours=8))


def sgt_now() -> datetime:
    """Current time as a timezone-aware datetime in SGT."""
    return datetime.now(SGT)


def sgt_today() -> date:
    """Today's calendar date in Singapore time."""
    return sgt_now().date()
