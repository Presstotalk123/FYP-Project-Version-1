"""Timing Gateway — per-class-group scheduled access windows for assessments.

The single place that resolves, for a given assessment + student, whether the
assessment is currently open for that student's class group and what the group's
window bounds are. Shared by the student join / detail / list endpoints and by the
lazy expiration check so they all agree.

Design notes (see the Timing Gateway plan):
- A "class group" is only a free-text ``User.class_group`` string — there is no
  ClassGroup entity — so windows are keyed by ``(assessment_id, class_group)`` in
  ``AssessmentClassWindow``.
- When ``Assessment.gateway_enabled`` is set, access is driven entirely by the
  window (``published`` AND ``start_at <= now < end_at``), superseding the manual
  ``is_running`` start/stop flag.
- The window ``end_at`` is stamped onto the session as its immovable
  ``hard_deadline`` at join. The student's *effective* deadline is the earlier of
  the personal timer (``end_time``, which moves with query-time credit) and this
  cap — implementing requirement #5 (min of the two).
- Enforcement stays lazy: there is no scheduler. Nothing here polls; callers invoke
  these helpers on requests they were already handling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.assessment_class_window import AssessmentClassWindow
from app.models.assessment_session import AssessmentSession
from app.models.user import User


class GatewayState(str, Enum):
    """Access state of a gateway assessment for a specific student's class group."""

    DISABLED = "disabled"      # gateway not enabled on this assessment
    NO_WINDOW = "no_window"    # gateway on, but the student's class group has no window
    UPCOMING = "upcoming"      # window exists, now < start_at
    OPEN = "open"              # start_at <= now < end_at
    CLOSED = "closed"          # now >= end_at


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Coerce a possibly-naive DB timestamp to timezone-aware UTC for safe comparison.

    SQLite hands back naive datetimes even for ``DateTime(timezone=True)`` columns;
    we treat those as UTC (everything in this app is stored in UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_window(
    db: Session, assessment_id: int, class_group: Optional[str]
) -> Optional[AssessmentClassWindow]:
    """The enabled window for this assessment + class group, or None."""
    if not class_group:
        return None
    return (
        db.query(AssessmentClassWindow)
        .filter(
            AssessmentClassWindow.assessment_id == assessment_id,
            AssessmentClassWindow.class_group == class_group,
            AssessmentClassWindow.is_enabled == 1,
        )
        .first()
    )


class ResolvedGateway:
    """Result of resolving the gateway for a student: state + window bounds (UTC)."""

    def __init__(
        self,
        state: GatewayState,
        window: Optional[AssessmentClassWindow] = None,
    ):
        self.state = state
        self.window = window
        self.start_at = _as_utc(window.start_at) if window else None
        self.end_at = _as_utc(window.end_at) if window else None

    @property
    def is_open(self) -> bool:
        return self.state == GatewayState.OPEN

    @property
    def is_gated(self) -> bool:
        """True when the gateway governs access (i.e. it is enabled)."""
        return self.state != GatewayState.DISABLED


def resolve_state(db: Session, assessment: Assessment, user: User) -> ResolvedGateway:
    """Resolve the gateway access state for ``user`` on ``assessment``."""
    if not getattr(assessment, "gateway_enabled", 0):
        return ResolvedGateway(GatewayState.DISABLED)

    window = get_window(db, assessment.id, user.class_group)
    if window is None:
        return ResolvedGateway(GatewayState.NO_WINDOW)

    now = _now()
    start = _as_utc(window.start_at)
    end = _as_utc(window.end_at)
    if now < start:
        return ResolvedGateway(GatewayState.UPCOMING, window)
    if now >= end:
        return ResolvedGateway(GatewayState.CLOSED, window)
    return ResolvedGateway(GatewayState.OPEN, window)


def effective_deadline(session: AssessmentSession) -> Optional[datetime]:
    """The earliest binding deadline for a session: min(end_time, hard_deadline).

    Returns None when neither is set (untimed attempt with no gateway cap). Values are
    normalized to timezone-aware UTC so callers can compare against ``datetime.now(utc)``.
    """
    candidates = [
        _as_utc(getattr(session, "end_time", None)),
        _as_utc(getattr(session, "hard_deadline", None)),
    ]
    present = [c for c in candidates if c is not None]
    return min(present) if present else None
