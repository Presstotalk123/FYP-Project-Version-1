"""Staff flags on students within one assessment.

See models/assessment_student_flag.py for what a flag is. All SQL for the
feature lives here; the endpoints stay thin, as with user_preferences.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.assessment_student_flag import AssessmentStudentFlag
from app.models.user import User

# Keeps a flag a short note. The API schema repeats this limit as max_length.
MAX_REASON_LENGTH = 500


@dataclass(frozen=True)
class FlagInfo:
    """One flag as the endpoints report it."""

    user_id: int
    reason: Optional[str]
    flagged_by: int
    flagged_by_email: Optional[str]
    flagged_at: Optional[datetime]


def clean_reason(reason: Optional[str]) -> Optional[str]:
    """Trim the reason. A blank reason becomes None.

    Raises ValueError when the trimmed reason is longer than MAX_REASON_LENGTH.
    """
    if reason is None:
        return None
    cleaned = reason.strip()
    if not cleaned:
        return None
    if len(cleaned) > MAX_REASON_LENGTH:
        raise ValueError(f"reason is longer than {MAX_REASON_LENGTH} characters")
    return cleaned


def _info(flag: AssessmentStudentFlag, staff_email: Optional[str]) -> FlagInfo:
    return FlagInfo(
        user_id=flag.user_id,
        reason=flag.reason,
        flagged_by=flag.flagged_by,
        flagged_by_email=staff_email,
        # The last time staff set the flag. created_at only when the row has
        # no updated_at yet (older rows on Postgres).
        flagged_at=flag.updated_at or flag.created_at,
    )


def _query(db: Session, assessment_id: int):
    return (
        db.query(AssessmentStudentFlag, User.email)
        .outerjoin(User, AssessmentStudentFlag.flagged_by == User.id)
        .filter(AssessmentStudentFlag.assessment_id == assessment_id)
    )


def flags_for_assessment(db: Session, *, assessment_id: int) -> dict[int, FlagInfo]:
    """Every flag on one assessment, keyed by student id."""
    return {flag.user_id: _info(flag, email) for flag, email in _query(db, assessment_id).all()}


def set_flag(
    db: Session, *, assessment_id: int, user_id: int, staff_id: int, reason: Optional[str]
) -> FlagInfo:
    """Create the flag, or replace its reason and staff user. Commits.

    One upsert rather than SELECT-then-INSERT, as in user_preferences.set_value:
    two staff users who flag the same student at the same time cannot trip the
    unique constraint. updated_at is set here because onupdate does not fire
    for ON CONFLICT DO UPDATE.
    """
    cleaned = clean_reason(reason)

    table = AssessmentStudentFlag.__table__
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    stmt = (
        insert(table)
        .values(assessment_id=assessment_id, user_id=user_id, reason=cleaned, flagged_by=staff_id)
        .on_conflict_do_update(
            index_elements=[table.c.assessment_id, table.c.user_id],
            set_={"reason": cleaned, "flagged_by": staff_id, "updated_at": func.now()},
        )
    )
    db.execute(stmt)
    db.commit()

    flag, email = (
        _query(db, assessment_id).filter(AssessmentStudentFlag.user_id == user_id).one()
    )
    return _info(flag, email)


def clear_flag(db: Session, *, assessment_id: int, user_id: int) -> bool:
    """Delete the flag. Returns False when there was none. Commits."""
    deleted = (
        db.query(AssessmentStudentFlag)
        .filter(
            AssessmentStudentFlag.assessment_id == assessment_id,
            AssessmentStudentFlag.user_id == user_id,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted > 0
