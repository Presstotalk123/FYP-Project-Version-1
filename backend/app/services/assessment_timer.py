"""
Configurable assessment timer — the single place the lazy-expiration rule and the
query-time credit system live, shared by the student router and the content-execution
endpoints (SQL question Run, SQL Lab Run/validate/submit).

Design (see the assessment timer spec):
- The backend `AssessmentSession.end_time` is the only source of truth. There is no
  backend countdown, scheduler, or polling job.
- Expiration is enforced *lazily*: whenever a student hits a mutating assessment
  endpoint, `enforce_not_expired` finalizes an overdue session and rejects the request.
- Query execution time is credited by pushing `end_time` forward (`credit_query_time`),
  so students don't lose assessment time while queries run.

`end_time` / `time_limit_minutes` being NULL means the attempt is untimed — every helper
here is then a no-op, so timed and untimed assessments share one code path.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.assessment_session import AssessmentSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_active_assessment_session(
    db: Session, assessment_id: int, user_id: int
) -> AssessmentSession | None:
    """The student's ongoing (is_active=1) session for this assessment, or None."""
    return (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.assessment_id == assessment_id,
            AssessmentSession.user_id == user_id,
            AssessmentSession.is_active == 1,
        )
        .first()
    )


def finalize_session(db: Session, session: AssessmentSession) -> None:
    """End & submit a session, preserving the student's work (no attempt/lab deletion).

    Shared by manual submit and lazy expiration so both produce the identical end state.
    """
    session.is_active = 0
    session.attempt_complete = 1  # single-attempt: lock out any future retake
    session.submitted_at = _now()
    db.commit()


def enforce_not_expired(db: Session, session: AssessmentSession | None) -> None:
    """Lazy expiration. If the session is timed and past its *effective* deadline,
    finalize it and reject the request. No-op for untimed attempts with no gateway cap
    (both `end_time` and `hard_deadline` NULL) or no session.

    The effective deadline is the earlier of the personal timer (`end_time`, which
    query-time credit pushes forward) and the Timing-Gateway cap (`hard_deadline`, the
    class-group window end, which never moves) — implementing the "student stops at the
    earlier of the two" rule. Importing `effective_deadline` here means every existing
    call site (SQL run, lab run/validate/submit, ER submit, final submit) inherits
    gateway enforcement for free.
    """
    from app.services.assessment_gateway import effective_deadline

    deadline = effective_deadline(session) if session is not None else None
    if deadline is None:
        return
    if session.is_active and _now() >= deadline:
        finalize_session(db, session)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assessment has ended.",
        )


def credit_query_time(
    db: Session, session: AssessmentSession | None, query_start: datetime
) -> None:
    """Credit the time a query took by extending the deadline: end_time += (now - query_start).
    No-op for untimed attempts.
    """
    if session is None or session.end_time is None:
        return
    session.end_time = session.end_time + (_now() - query_start)
    db.commit()
