"""Who counts as "registered" for an assessment.

There is no enrolment table in this codebase: access is granted either by a Timing-Gateway
window matched on the free-text ``User.class_group``, or by manually running the assessment.
The pre-registration source of truth is ``whitelist_entries`` — staff add students there
before they ever log in — unioned with real ``users`` so a student who signed up without a
whitelist row still counts exactly once.

Deliberately NOT cached. These counts are the denominator of every "attempted / registered"
figure; caching them would mean whitelist edits silently fail to move the denominator until
the ASSESSMENT_ANALYTICS version happened to bump.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.assessment_class_window import AssessmentClassWindow
from app.models.user import User, UserRole
from app.models.whitelist import WhitelistEntry


def assessment_class_groups(db: Session, assessment: Assessment) -> Optional[list[str]]:
    """Class groups gating this assessment, or None meaning "everyone".

    Only the Timing Gateway restricts who may sit an assessment. With it off — or on but with
    no enabled window configured — there is no per-group restriction, so every registered
    student is in scope and None is returned.
    """
    if not assessment.gateway_enabled:
        return None
    rows = (
        db.query(AssessmentClassWindow.class_group)
        .filter(
            AssessmentClassWindow.assessment_id == assessment.id,
            AssessmentClassWindow.is_enabled == 1,
        )
        .distinct()
        .all()
    )
    groups = [cg for (cg,) in rows if cg]
    return groups or None


def registered_emails(db: Session, class_groups: Optional[list[str]] = None) -> set[str]:
    """Distinct lowercased emails of students registered for a scope.

    Whitelist entries unioned with real user accounts. Lowercasing is what dedupes the two
    sources: the same student appears in both once they log in. Passing an empty list means
    "no groups", which correctly yields an empty set.
    """
    user_q = db.query(User.email).filter(User.role == UserRole.STUDENT)
    wl_q = db.query(WhitelistEntry.email).filter(WhitelistEntry.role == UserRole.STUDENT)
    if class_groups is not None:
        user_q = user_q.filter(User.class_group.in_(class_groups))
        wl_q = wl_q.filter(WhitelistEntry.class_group.in_(class_groups))
    emails = {email.lower() for (email,) in user_q.all() if email}
    emails |= {email.lower() for (email,) in wl_q.all() if email}
    return emails


def registered_count(db: Session, class_groups: Optional[list[str]] = None) -> int:
    """How many distinct students are registered for a scope."""
    return len(registered_emails(db, class_groups))


def signed_in_student_count(db: Session) -> int:
    """Students who have logged in at least once, i.e. who have a real user row.

    Paired with ``registered_count(db, None)`` on the dashboard: the gap between them is the
    sign-up rate.
    """
    return db.query(User.id).filter(User.role == UserRole.STUDENT).count()
