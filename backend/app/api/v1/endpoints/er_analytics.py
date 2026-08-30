"""Staff-only analytics over er_submissions. Same /er-diagram URL prefix as the
main ERD router, kept in its own module so er_diagram.py stops growing."""
import asyncio
import json
import logging
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
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
from app.services import er_regrade, er_staff_submission
from app.utils.er_storage import get_er_storage_provider
from app.services.er_analytics import (
    class_overview,
    list_class_groups,
    question_analytics,
    student_engagement,
    student_submissions,
)
from app.services.er_score_override import (
    ScoreOverrideError,
    is_latest_attempt,
    apply_override,
    revert_override,
    with_earned_points,
)

logger = logging.getLogger(__name__)

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
        # Non-null when a rubric regrade replaced this attempt's grade.
        "regraded_at": row.regraded_at.isoformat() if row.regraded_at else None,
        # The most recent attempt — the one whose grade the tutor conversation
        # mirrors. The assessment mark itself follows the student's BEST grade
        # (assessment_scoring.er_best_scores_bulk), whichever attempt carries it.
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
    analytics aggregates read it directly, the assessment mark re-derives from the
    student's best grade, and the grade the student sees follows when this is
    their latest attempt.

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


@router.get("/analytics/students")
def get_student_engagement(
    class_group: Optional[str] = None,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """Per-student ERD engagement (practice volume, assessment score, Baloo
    usage), for the admin ERD tab."""
    return cache_read(
        db,
        Ns.ER_ANALYTICS,
        key=("students", class_group or ""),
        producer=lambda: student_engagement(db, class_group),
    )


class RegradeRequest(BaseModel):
    """Scope for a regrade run. `class_group` limits it to one group's students;
    None means every submission of the question."""
    class_group: Optional[str] = None


@router.post("/questions/{question_id}/regrade")
async def start_question_regrade(
    question_id: int,
    body: RegradeRequest,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """Regrade every stored submission of this question against its current
    rubric, staff overrides included. An explicit staff choice — the rubric
    editor offers it after a save, it never runs on its own.

    Runs as a background job (one per question) because a full class is many
    30-90 s pipeline runs — far past any request timeout. Progress is read from
    the status endpoint below. Each row commits on its own, so a crashed job
    keeps every grade it already produced and a re-run continues safely.
    """
    if settings.ERD_TUTOR_ENGINE != "langgraph":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Regrading requires the langgraph grading engine.",
        )
    # Normalized to the family master: assessment attempts are stored on clone
    # questions, the master's rubric is the one staff edit, and one job key per
    # family keeps two entry points from racing over the same rows.
    master_id = er_regrade.family_master_id(db, question_id)
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == master_id,
                ERDiagramQuestion.is_deleted == 0)
        .first()
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Question not found")
    if er_regrade.count_submissions(db, master_id, body.class_group) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "No submissions match this scope."
                if body.class_group
                else "This question has no submissions to regrade."
            ),
        )
    try:
        return er_regrade.start_regrade(master_id, body.class_group)
    except er_regrade.RegradeAlreadyRunning as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get("/questions/{question_id}/regrade/status")
def get_question_regrade_status(
    question_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """Snapshot of the question's regrade job, or {"exists": false} when none
    ran since startup. Jobs are keyed by the family master, so a clone id polls
    the same job. In-process registry: under several workers a poll can land on
    a worker that never saw the job."""
    snapshot = er_regrade.job_status(er_regrade.family_master_id(db, question_id))
    if snapshot is None:
        return {"exists": False}
    return {"exists": True, **snapshot}


@router.get("/questions/{question_id}/students/{student_id}/draft")
def get_student_draft(
    question_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """A student's autosaved canvas, for staff.

    The student-facing GET /er-diagram/draft is scoped to the caller and never
    accepts a user id, so staff need their own way in. Used before grading: the
    dialog renders this XML to a PNG so the stored attempt carries a picture, and
    it lets staff see the diagram before they commit to a mark.
    """
    try:
        draft = er_staff_submission.load_draft(
            db, user_id=student_id, question_id=question_id
        )
    except er_staff_submission.NoDiagram:
        return {"exists": False}
    return {
        "exists": True,
        "revision": draft.revision,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
        "xml": draft.xml,
    }


@router.post("/questions/{question_id}/students/{student_id}/submission")
async def add_student_submission(
    question_id: int,
    student_id: int,
    reason: str = Form(""),
    use_saved_draft: bool = Form(False),
    submission_xml_text: Optional[str] = Form(None),
    regrade: bool = Form(False),
    erd_img: Optional[UploadFile] = File(None),
    rendered_png: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    staff: User = Depends(require_staff_role),
):
    """Create a graded ER submission for a student, from a diagram staff supply.

    Why this exists: the assessment timer closes the session without submitting the
    open diagram, so a student who ran out of time has work but no grade. The
    student's own submit path is the only other writer of these rows, so this goes
    through the same service and writes the same fields. `added_by_staff_id` is what
    separates the two afterwards.

    Async, not sync: nearly all of the 30-90 s is spent awaiting the LLM over HTTP,
    so a sync handler would pin a threadpool worker for the whole wait while doing
    nothing. The service pushes its blocking writes to a worker thread.

    One long response rather than a job, because staff run this for a handful of
    students. A plain JSON handler is not cancelled by a client disconnect, so a
    closed tab loses the response but not the grade.

    `rendered_png` is a picture of the XML source, drawn by the browser before the
    request. It is stored so the attempt has something to look at in analytics, and
    is never graded — grading reads the XML, which is exact. It is not a source, so
    it does not count toward the one-source rule below.
    """
    # Optional, and stored as NULL when blank. `added_by_staff_id` is what marks the
    # row as staff-added; the reason is a note for whoever reads it later, not proof.
    # The 500 cap is a storage guard, not a demand for detail.
    clean_reason = (reason or "").strip() or None
    if clean_reason is not None and len(clean_reason) > 500:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="The reason must be 500 characters or fewer.")

    # Exactly one source, mirroring the student endpoint's rule for
    # submission_xml_text XOR erd_img. Two sources would silently grade one of them.
    has_upload = erd_img is not None and bool(getattr(erd_img, "filename", ""))
    given = [bool(use_saved_draft), bool((submission_xml_text or "").strip()), has_upload]
    if sum(1 for value in given if value) != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Give exactly one source: the saved draft, XML text, or an image.",
        )

    student = db.query(User).filter(User.id == student_id).first()
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id,
                ERDiagramQuestion.is_deleted == 0)
        .first()
    )
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    xml_text = None
    image_bytes = None
    image_key = None

    if use_saved_draft:
        source = "draft"
        try:
            xml_text = er_staff_submission.load_draft_xml(
                db, user_id=student_id, question_id=question_id
            )
        except er_staff_submission.NoDiagram as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    elif has_upload:
        source = "image"
        image_bytes = await erd_img.read()
        # Stored so ER Analytics can show the diagram. The XML sources hold no
        # picture, so this is the only path that fills submitted_image_storage_key.
        await erd_img.seek(0)
        image_key, _url = await asyncio.to_thread(get_er_storage_provider().save, erd_img)
    else:
        source = "xml"
        xml_text = submission_xml_text.strip()
        if len(xml_text) > settings.ER_MAX_XML_CHARS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"xml exceeds maximum length of {settings.ER_MAX_XML_CHARS} characters",
            )

    # A browser-drawn picture of an XML source. Best effort by design: if storing it
    # fails, the attempt is still graded and simply has no thumbnail, exactly as
    # before this existed. Never overrides a real uploaded image.
    if image_key is None and rendered_png is not None and getattr(rendered_png, "filename", ""):
        try:
            image_key, _url = await asyncio.to_thread(
                get_er_storage_provider().save, rendered_png
            )
        except Exception:
            logger.exception("add_student_submission: rendered_png not stored; grading continues")

    try:
        result = await er_staff_submission.grade_and_record(
            db,
            user_id=student_id,
            question=question,
            xml_text=xml_text,
            image_bytes=image_bytes,
            image_storage_key=image_key,
            source=source,
            staff_id=staff.id,
            reason=clean_reason,
            regrade=regrade,
        )
    except er_staff_submission.AlreadyGraded as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except er_staff_submission.NoDiagram as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except er_staff_submission.GradingFailed as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return {
        "submission_id": result.submission_id,
        "score": result.score,
        "source": result.source,
        "added_by": staff.email,
    }
