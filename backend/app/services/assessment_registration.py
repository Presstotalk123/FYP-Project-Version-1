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

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.assessment import Assessment
from app.models.assessment_class_window import AssessmentClassWindow
from app.models.user import User, UserRole
from app.models.whitelist import WhitelistEntry


def excluded_class_groups() -> list[str]:
    """Staff/test class groups that never count as participants (see config)."""
    return settings.ANALYTICS_EXCLUDED_CLASS_GROUPS or []


def exclude_test_groups(query, column):
    """Drop staff/test groups from a query.

    ``NOT IN`` evaluates to NULL — and therefore filters out the row — when the column is
    NULL, so a student with no class group at all would silently vanish. The explicit
    IS NULL branch keeps them.
    """
    excluded = excluded_class_groups()
    if not excluded:
        return query
    return query.filter(or_(column.is_(None), column.notin_(excluded)))


def assessment_class_groups(db: Session, assessment: Assessment) -> Optional[list[str]]:
    """Class groups gating this assessment. None means "everyone"; [] means "nobody".

    Only the Timing Gateway restricts who may sit an assessment, so with it off there is no
    per-group restriction and None is returned.

    With the gateway ON but no enabled window configured, the gateway resolves to NO_WINDOW
    for every student — nobody can sit it. That returns an empty list, NOT None: treating it
    as "unrestricted" would report the whole cohort as registered for an assessment no one
    can access (e.g. "0/312 started" the moment staff enable the gateway before scheduling).
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
    return [cg for (cg,) in rows if cg]


def registered_emails(db: Session, class_groups: Optional[list[str]] = None) -> set[str]:
    """Distinct lowercased emails of students registered for a scope.

    Whitelist entries unioned with real user accounts. Lowercasing is what dedupes the two
    sources: the same student appears in both once they log in. Passing an empty list means
    "no groups", which correctly yields an empty set. Staff/test groups are always excluded.
    """
    user_q = db.query(User.email).filter(User.role == UserRole.STUDENT)
    wl_q = db.query(WhitelistEntry.email).filter(WhitelistEntry.role == UserRole.STUDENT)
    if class_groups is not None:
        user_q = user_q.filter(User.class_group.in_(class_groups))
        wl_q = wl_q.filter(WhitelistEntry.class_group.in_(class_groups))
    user_q = exclude_test_groups(user_q, User.class_group)
    wl_q = exclude_test_groups(wl_q, WhitelistEntry.class_group)
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


def registered_students(
    db: Session, class_groups: Optional[list[str]] = None
) -> list[dict]:
    """Registered students for a scope, with identity — the counting counterpart of
    ``registered_emails``.

    Deduped on lowercased email. A real ``users`` row WINS over a whitelist row for name and
    class group: the account reflects what the student is now, the whitelist only what staff
    pre-registered. Returned sorted by email so callers have a stable order before their own
    sort is applied.
    """
    wl_q = db.query(
        WhitelistEntry.email, WhitelistEntry.name, WhitelistEntry.class_group
    ).filter(WhitelistEntry.role == UserRole.STUDENT)
    user_q = db.query(User.email, User.name, User.class_group).filter(
        User.role == UserRole.STUDENT
    )
    if class_groups is not None:
        wl_q = wl_q.filter(WhitelistEntry.class_group.in_(class_groups))
        user_q = user_q.filter(User.class_group.in_(class_groups))
    wl_q = exclude_test_groups(wl_q, WhitelistEntry.class_group)
    user_q = exclude_test_groups(user_q, User.class_group)

    by_email: dict[str, dict] = {}
    # Whitelist first so the user rows below overwrite them.
    for email, name, group in wl_q.all():
        if email:
            by_email[email.lower()] = {
                "email": email.lower(), "name": name, "class_group": group,
            }
    for email, name, group in user_q.all():
        if email:
            by_email[email.lower()] = {
                "email": email.lower(), "name": name, "class_group": group,
            }
    return sorted(by_email.values(), key=lambda r: r["email"])
