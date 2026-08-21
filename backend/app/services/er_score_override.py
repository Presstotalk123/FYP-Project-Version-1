"""Staff corrections to a graded ERD submission.

A correction is expressed as points earned per check. The grader can only award
all, half or none of a check — its statuses are pass/partial/fail — but a person
marking by hand needs the room between those, so staff set a number and the
status is derived from it.

That is the one place this diverges from `compute_grade`, which derives the
points from the status and so cannot express 13 of 18. Everything else is shared:
the same weights, the same must/should rule, the same rounding, and `_label` from
the scorer itself, so a corrected attempt is labelled exactly as a graded one.

Weights come from the submission's OWN stored checks, not the question's current
rubric_json: a rubric can be edited after an attempt is graded, and scoring
against today's version would mark the student on criteria they never saw.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.er_submission import ErSubmission
from app.core.cache import Ns, bump_version
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.services import assessment_scoring
from app.services.erd_tutor.scoring import _label

SCORING_LEVELS = {"must", "should"}


class ScoreOverrideError(ValueError):
    """Rejected input. Raised with a message meant for the person who typed it."""


def _stored_checks(submission: ErSubmission) -> list[dict]:
    try:
        checks = json.loads(submission.checks_json) if submission.checks_json else []
    except (TypeError, ValueError):
        checks = []
    if not isinstance(checks, list):
        return []
    return [c for c in checks if isinstance(c, dict) and str(c.get("id", "")).strip()]


def _snapshot(submission: ErSubmission) -> str:
    """The grade as it stands now, as JSON — frozen before the first override."""
    return json.dumps(
        {
            "score": {
                "earned_points": submission.score_earned,
                "total_points": submission.score_total,
                "percent": submission.score_percent,
                "label": submission.score_label,
            },
            "checks": _stored_checks(submission),
        },
        ensure_ascii=False,
    )


def is_latest_attempt(db: Session, submission: ErSubmission) -> bool:
    """Whether this is the student's most recent attempt at this question.

    Only the latest one describes where the student ended up, and only that is
    allowed to move their assessment mark — see apply_override.
    """
    latest_id = (
        db.query(ErSubmission.id)
        .filter(
            ErSubmission.user_id == submission.user_id,
            ErSubmission.er_diagram_question_id == submission.er_diagram_question_id,
        )
        .order_by(ErSubmission.created_at.desc(), ErSubmission.id.desc())
        .limit(1)
        .scalar()
    )
    return latest_id == submission.id


def _sync_conversation(db: Session, submission: ErSubmission, grade: dict) -> bool:
    """Push a corrected grade onto the tutor conversation, which is what the
    student sees and what assessment scoring reads. Returns whether it happened.

    Skipped for anything but the latest attempt: the conversation holds one
    grade, the student's current standing, and rewriting it from a superseded
    attempt would mark them on work they had already replaced.
    """
    if not is_latest_attempt(db, submission):
        return False
    conversation = (
        db.query(ErdTutorConversation)
        .filter(
            ErdTutorConversation.user_id == submission.user_id,
            ErdTutorConversation.er_diagram_question_id == submission.er_diagram_question_id,
            ErdTutorConversation.context_type == "standalone",
        )
        .first()
    )
    if conversation is None:
        return False
    conversation.last_submit_score = json.dumps(grade["score"], ensure_ascii=False)

    # Merge into the stored report rather than replacing it. The report also holds
    # the tutor's narrative — student_message, top_issues, the IBL state — which a
    # correction has no business rewriting, and which a synthetic judge result does
    # not carry: replacing it wholesale blanked the feedback the student reads.
    try:
        report = json.loads(conversation.last_submit_report or "{}")
    except (TypeError, ValueError):
        report = {}
    if not isinstance(report, dict):
        report = {}
    report["score"] = grade["score"]
    report["checks"] = grade["checks"]
    conversation.last_submit_report = json.dumps(report, ensure_ascii=False)
    return True


def _propagate_to_assessment(db: Session, submission: ErSubmission) -> None:
    """Carry a corrected ER mark through to the assessment views.

    `_sync_conversation` alone is not enough. The roster table reads a cached
    per-student score, and the staff activity panel reads a total frozen at
    finalization; neither is invalidated by a conversation or submission write
    (see core/cache.py, which deliberately leaves ASSESSMENT_ANALYTICS alone while
    an exam is running). Without both steps a corrected mark shows in ER analytics
    and nowhere else.

    Only called when the conversation was actually synced, because only then did
    the student's standing change.
    """
    bump_version(db, Ns.ASSESSMENT_ANALYTICS)
    assessment_scoring.refresh_frozen_weighted_score(
        db,
        er_question_id=submission.er_diagram_question_id,
        user_id=submission.user_id,
    )


def _num(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _scores(check: dict) -> bool:
    """Whether a check contributes to the total at all."""
    return (
        check.get("requirement_level") in SCORING_LEVELS
        and check.get("status") != "not_applicable"
    )


def _earned_from_status(check: dict) -> float:
    """What the grader awarded, in points — the inverse of compute_grade's rule."""
    points = _num(check.get("points"))
    status = check.get("status")
    if status == "pass":
        return points
    if status == "partial":
        return 0.5 * points
    return 0.0


def with_earned_points(check: dict) -> dict:
    """`check` guaranteed to carry `earned_points`, derived when it is absent.

    Attempts graded before compute_grade recorded the award keep only `points`
    (the check's maximum) and `status`, which made the staff "Awarded" column read
    0 for every AI-graded check while the overall score was right. Filling on read
    fixes those without a migration.

    An existing value is never recomputed: a staff correction can award a figure
    no status can express (13 of 18), and deriving over the top would undo it.
    Non-scoring checks are left alone, matching what both graders emit.
    """
    if "earned_points" in check or not _scores(check):
        return check
    return {**check, "earned_points": _earned_from_status(check)}


def _status_from_earned(earned: float, points: float) -> str:
    """Everything between none and all is `partial`, which is the only status the
    rest of the system understands — the exact figure lives in the points."""
    if points <= 0:
        return "not_applicable"
    if earned >= points:
        return "pass"
    if earned <= 0:
        return "fail"
    return "partial"


def score_from_awards(checks: list[dict], awards: dict[str, float]) -> dict:
    """Re-total a submission from points awarded per check.

    `awards` maps check id -> points earned and need only cover what changed;
    anything omitted keeps what the grader awarded. Mirrors compute_grade's
    output shape so callers and storage do not care which produced a grade.
    """
    final_checks: list[dict] = []
    earned_total = 0.0
    points_total = 0.0

    for check in checks:
        cid = str(check.get("id", "")).strip()
        points = _num(check.get("points"))
        scoring = _scores(check)
        awarded = awards.get(cid)
        earned = _earned_from_status(check) if awarded is None else _num(awarded)

        if scoring:
            points_total += points
            earned_total += earned
            status = _status_from_earned(earned, points)
        else:
            # Not evaluated, or optional: excluded from the total either way, and
            # its status is not something a points figure can speak to.
            status = check.get("status", "not_applicable")

        out = dict(check)
        out["status"] = status
        out["points"] = points
        if scoring:
            out["earned_points"] = earned
        final_checks.append(out)

    percent = round(100 * earned_total / points_total) if points_total > 0 else 0
    return {
        "score": {
            "label": _label(percent),
            "earned_points": earned_total,
            "total_points": points_total,
            "percent": percent,
        },
        "checks": final_checks,
    }


def apply_override(
    db: Session,
    submission: ErSubmission,
    awards: dict[str, float],
    reason: str,
    staff_id: int,
) -> dict[str, Any]:
    """Re-score a submission from points staff awarded per check.

    `awards` maps check id -> points earned and may cover only the checks being
    changed; anything omitted keeps what the grader awarded.
    """
    # Optional: who and when are recorded regardless, and demanding a sentence on
    # every edit is friction on the common case where the change is self-evident.
    reason = (reason or "").strip()

    stored = _stored_checks(submission)
    if not stored:
        raise ScoreOverrideError("This submission has no stored checks to adjust.")

    by_id = {str(c["id"]).strip(): c for c in stored}
    unknown = sorted(set(awards) - set(by_id))
    if unknown:
        raise ScoreOverrideError(f"Unknown check id(s): {', '.join(unknown)}")

    for cid, value in awards.items():
        check = by_id[cid]
        if not _scores(check):
            raise ScoreOverrideError(
                f"{cid} was not evaluated for this attempt, so it carries no points."
            )
        try:
            awarded = float(value)
        except (TypeError, ValueError):
            raise ScoreOverrideError(f"{cid}: points must be a number.")
        points = _num(check.get("points"))
        # Bounded by the check's own weight: awarding more than a check is worth
        # would make the total exceed itself and the percentage exceed 100.
        if awarded < 0 or awarded > points:
            raise ScoreOverrideError(f"{cid}: points must be between 0 and {points:g}.")

    # Freeze the grader's result before the first correction, never after: the
    # question "what did the AI say" must keep one answer across re-corrections.
    if submission.original_grade_json is None:
        submission.original_grade_json = _snapshot(submission)

    grade = score_from_awards(stored, {k: float(v) for k, v in awards.items()})

    # Attribute the checks staff actually moved, so the student is not told the
    # grader found something it never did. Without a reason the attribution still
    # stands on its own — what changed matters more than the sentence about it.
    note = f"Adjusted by staff: {reason}" if reason else "Adjusted by staff."
    for out in grade["checks"]:
        if str(out.get("id", "")).strip() in awards:
            out["brief_reason"] = note

    score = grade["score"]
    submission.score_earned = score["earned_points"]
    submission.score_total = score["total_points"]
    submission.score_percent = score["percent"]
    submission.score_label = score["label"]
    submission.checks_json = json.dumps(grade["checks"], ensure_ascii=False)
    submission.override_reason = reason or None
    submission.overridden_by = staff_id
    submission.overridden_at = datetime.now(timezone.utc)

    mark_updated = _sync_conversation(db, submission, grade)
    if mark_updated:
        _propagate_to_assessment(db, submission)
    db.commit()
    return {"grade": grade, "assessment_mark_updated": mark_updated}


def revert_override(db: Session, submission: ErSubmission) -> dict[str, Any]:
    """Restore the grader's original result and clear the correction."""
    if submission.original_grade_json is None:
        raise ScoreOverrideError("This submission has not been overridden.")

    try:
        original = json.loads(submission.original_grade_json)
    except (TypeError, ValueError) as exc:
        raise ScoreOverrideError("The stored original grade could not be read.") from exc

    score = original.get("score") or {}
    submission.score_earned = score.get("earned_points")
    submission.score_total = score.get("total_points")
    submission.score_percent = score.get("percent")
    submission.score_label = score.get("label")
    submission.checks_json = json.dumps(original.get("checks") or [], ensure_ascii=False)
    submission.override_reason = None
    submission.overridden_by = None
    submission.overridden_at = None
    submission.original_grade_json = None

    mark_updated = _sync_conversation(
        db, submission, {"score": score, "checks": original.get("checks") or []}
    )
    if mark_updated:
        _propagate_to_assessment(db, submission)
    db.commit()
    return {"grade": original, "assessment_mark_updated": mark_updated}
