"""Staff-only analytics over er_submissions. Same /er-diagram URL prefix as the
main ERD router, kept in its own module so er_diagram.py stops growing."""
import json
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import Ns, cache_read
from app.database import get_db
from app.dependencies import require_staff_role
from app.models.er_submission import ErSubmission
from app.models.user import User
from app.services.er_analytics import (
    class_overview,
    list_class_groups,
    question_analytics,
    student_submissions,
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
        "checks": json.loads(row.checks_json) if row.checks_json else [],
        "submission_description": row.submission_description,
        "submitted_xml": row.submitted_xml,
        "has_image": bool(row.submitted_image_storage_key),
        "hint_level_at_submit": row.hint_level_at_submit,
        "ibl_stage_at_submit": row.ibl_stage_at_submit,
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
