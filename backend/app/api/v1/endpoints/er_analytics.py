"""Staff-only analytics over er_submissions. Same /er-diagram URL prefix as the
main ERD router, kept in its own module so er_diagram.py stops growing."""
import json
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import Ns, cache_read
from app.database import get_db
from app.dependencies import require_staff_role
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.er_submission import ErSubmission
from app.models.user import User
from app.services.er_analytics import (
    class_overview,
    list_class_groups,
    question_analytics,
    student_submissions,
)
from app.services.er_score_override import (
    ScoreOverrideError,
    is_latest_attempt,
    apply_override,
    revert_override,
    with_earned_points,
)

router = APIRouter(prefix="/er-diagram", tags=["er-analytics"])

Context = Literal["practice", "assessment", "all"]


@router.get("/questions/{question_id}/analytics")
def get_question_analytics(
    question_id: int,
    context: Context = "all",
    class_group: Optional[str] = None,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    # Version-stamped cache: invalidated automatically whenever a submission,
    # chat message or user (class group) changes — repeated staff refreshes
    # between changes skip the whole aggregation.
    out = cache_read(
        db,
        Ns.ER_ANALYTICS,
        key=("question", question_id, context, class_group or ""),
        producer=lambda: question_analytics(db, question_id, context, class_group),
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Question not found")
    return out


@router.get("/analytics/class-groups")
def get_class_groups(
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """Distinct class groups from Manage Users, for the analytics filter."""
    return cache_read(
        db,
        Ns.ER_ANALYTICS,
        key=("class-groups",),
        producer=lambda: {"class_groups": list_class_groups(db)},
    )


@router.get("/questions/{question_id}/students/{student_id}/submissions")
def get_student_submissions(
    question_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    return student_submissions(db, question_id, student_id)


def _submission_or_404(db: Session, submission_id: int) -> ErSubmission:
    row = db.query(ErSubmission).filter(ErSubmission.id == submission_id).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Submission not found")
    return row


def _override_view(db: Session, row: ErSubmission) -> Optional[dict]:
    """Who corrected this attempt, when, why, and what the grader had said."""
    if row.overridden_at is None:
        return None
    try:
        original = json.loads(row.original_grade_json) if row.original_grade_json else {}
    except (TypeError, ValueError):
        original = {}
    email = (
        db.query(User.email).filter(User.id == row.overridden_by).scalar()
        if row.overridden_by else None
    )
    return {
        "reason": row.override_reason,
        "by_user_id": row.overridden_by,
        "by_email": email,
        "at": row.overridden_at.isoformat(),
        "original_score": (original.get("score") or {}),
        "original_checks": (original.get("checks") or []),
    }


def _enriched_checks(db: Session, row: ErSubmission, checks: list[dict]) -> list[dict]:
    """Prepare stored checks for the staff view: pass_criteria, and what was awarded.

    A stored check keeps only what grading needed — id, points, status, reason —
    so on its own it cannot tell staff what "A1" was actually testing. Criteria are
    joined here rather than persisted per submission because the text is the same
    for every attempt at a question.

    A rubric edited since the attempt may no longer describe some check; those
    simply come back without criteria rather than with the wrong ones.

    `earned_points` is filled in for attempts graded before compute_grade recorded
    it — see er_score_override.with_earned_points, which also guarantees a staff
    correction is never recomputed from its status.
    """
    rubric = (
        db.query(ERDiagramQuestion.rubric_json)
        .filter(ERDiagramQuestion.id == row.er_diagram_question_id)
        .scalar()
    )
    if isinstance(rubric, str):
        try:
            rubric = json.loads(rubric)
        except (TypeError, ValueError):
            rubric = None
    criteria = {
        str(c.get("id", "")).strip(): c.get("pass_criteria", "")
        for c in ((rubric or {}).get("checks") or [])
        if isinstance(c, dict)
    }
    return [{**with_earned_points(c),
             "pass_criteria": criteria.get(str(c.get("id", "")).strip(), "")}
            for c in checks]


@router.get("/submissions/{submission_id}")
def get_submission_detail(
    submission_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    row = _submission_or_404(db, submission_id)
    return {
        "id": row.id,
        "user_id": row.user_id,
        "question_id": row.er_diagram_question_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "score_earned": row.score_earned,
        "score_total": row.score_total,
        "score_percent": row.score_percent,
        "score_label": row.score_label,
        "checks": _enriched_checks(db, row, json.loads(row.checks_json) if row.checks_json else []),
        "submission_description": row.submission_description,
        "submitted_xml": row.submitted_xml,
        "has_image": bool(row.submitted_image_storage_key),
        "hint_level_at_submit": row.hint_level_at_submit,
        "ibl_stage_at_submit": row.ibl_stage_at_submit,
        # Override provenance. `override` is null for an untouched attempt, so the
        # UI can tell "graded by the AI" from "corrected by a person".
        "override": _override_view(db, row),
        # Whether adjusting this attempt would move the student's mark. Shown up
        # front so staff are not surprised by a correction that only lands in
        # analytics — see er_score_override._sync_conversation.
        "is_latest_attempt": is_latest_attempt(db, row),
    }


class ScoreOverrideRequest(BaseModel):
    """Points awarded per check id. Only the checks being changed need sending;
    the rest keep what the grader awarded."""
    checks: dict[str, float] = Field(default_factory=dict)
    reason: str = ""


@router.put("/submissions/{submission_id}/score")
def override_submission_score(
    submission_id: int,
    body: ScoreOverrideRequest,
    db: Session = Depends(get_db),
    staff: User = Depends(require_staff_role),
):
    """Correct a graded attempt. The corrected score becomes the truth everywhere:
    analytics aggregates read it directly, and the student's mark follows when this
    is their latest attempt.

    Mutating the ORM row is what invalidates the analytics cache — the after_flush
    listener watches session.dirty, so no explicit bump is needed here.
    """
    row = _submission_or_404(db, submission_id)
    try:
        result = apply_override(db, row, body.checks, body.reason, staff.id)
    except ScoreOverrideError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {
        "score": result["grade"]["score"],
        "checks": _enriched_checks(db, row, result["grade"]["checks"]),
        "assessment_mark_updated": result["assessment_mark_updated"],
        "override": _override_view(db, row),
    }


@router.delete("/submissions/{submission_id}/score")
def revert_submission_score(
    submission_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """Put the grader's original result back and drop the correction."""
    row = _submission_or_404(db, submission_id)
    try:
        result = revert_override(db, row)
    except ScoreOverrideError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {
        "score": result["grade"].get("score", {}),
        "checks": _enriched_checks(db, row, result["grade"].get("checks", [])),
        "assessment_mark_updated": result["assessment_mark_updated"],
        "override": None,
    }


@router.get("/submissions/{submission_id}/image")
def get_submission_image(
    submission_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    row = _submission_or_404(db, submission_id)
    key = row.submitted_image_storage_key
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No image stored for this submission")
    # Keys are server-generated UUID filenames; anything with path separators
    # is not ours. Belt-and-braces against traversal via a tampered DB row.
    if "/" in key or "\\" in key or ".." in key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Image file missing from storage")
    # Local provider stores flat UUID-named files in ER_DIAGRAM_UPLOAD_PATH.
    # Azure serving is deferred (spec: local/demo first).
    path = Path(settings.ER_DIAGRAM_UPLOAD_PATH) / key
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Image file missing from storage")
    return FileResponse(path)


@router.get("/analytics/overview")
def get_class_overview(
    context: Context = "all",
    class_group: Optional[str] = None,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    return cache_read(
        db,
        Ns.ER_ANALYTICS,
        key=("overview", context, class_group or ""),
        producer=lambda: class_overview(db, context, class_group),
    )
