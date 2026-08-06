from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models.user import User
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.models.assessment_item_visit import AssessmentItemVisit
from app.schemas.student_assessment import (
    StudentAssessmentListItem,
    StudentAssessmentDetail,
    StudentAssessmentItemView,
    AssessmentSessionResponse,
    ItemVisitResponse,
)
from app.dependencies import get_current_user
from app.api.v1.endpoints.assessments import _resolve_item_title
from app.services.assessment_timer import finalize_session
from app.services import assessment_scoring
from app.core.cache import cache_read, assessment_body_ns

router = APIRouter(prefix="/student-assessments", tags=["student-assessments"])


class JoinRequest(BaseModel):
    password: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_published_assessment(assessment_id: int, db: Session) -> Assessment:
    assessment = (
        db.query(Assessment)
        .filter(
            Assessment.id == assessment_id,
            Assessment.is_published == 1,
            Assessment.is_deleted == 0,
        )
        .first()
    )
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return assessment


def _get_active_session(assessment_id: int, user_id: int, db: Session) -> AssessmentSession | None:
    return (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.assessment_id == assessment_id,
            AssessmentSession.user_id == user_id,
            AssessmentSession.is_active == 1,
        )
        .first()
    )


def _get_completed_session(assessment_id: int, user_id: int, db: Session) -> AssessmentSession | None:
    """Return the student's submitted session (attempt_complete=1) if one exists.

    Independent of is_active: assessments are single-attempt, so once a session is
    completed the student is locked out of retaking it.
    """
    return (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.assessment_id == assessment_id,
            AssessmentSession.user_id == user_id,
            AssessmentSession.attempt_complete == 1,
        )
        .first()
    )


def _build_item_view(item: AssessmentItem, visited: bool, db: Session) -> StudentAssessmentItemView:
    return StudentAssessmentItemView(
        id=item.id,
        item_type=item.item_type,
        item_id=item.item_id,
        order_index=item.order_index,
        weight=item.weight,
        item_title=_resolve_item_title(item, db),
        visited=visited,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[StudentAssessmentListItem])
def list_student_assessments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessments = (
        db.query(Assessment)
        .filter(Assessment.is_published == 1, Assessment.is_deleted == 0)
        .order_by(Assessment.created_at.desc())
        .all()
    )

    items: List[StudentAssessmentListItem] = []
    for a in assessments:
        # Per-user attempt state. The completed session (if any) carries the submission
        # time; the weighted score is only surfaced once results are released (assessment
        # stopped), mirroring get_student_assessment's not-running branch.
        completed = _get_completed_session(a.id, current_user.id, db)
        attempt_complete = completed is not None
        weighted_score = (
            assessment_scoring.compute_weighted_score(db, a, current_user.id)
            if attempt_complete and not a.is_running
            else None
        )
        items.append(
            StudentAssessmentListItem(
                id=a.id,
                title=a.title,
                description=a.description,
                is_running=bool(a.is_running),
                has_password=bool(a.password),
                attempt_complete=attempt_complete,
                weighted_score=weighted_score,
                submitted_at=completed.submitted_at if completed else None,
            )
        )
    return items


@router.get("/{assessment_id}", response_model=StudentAssessmentDetail)
def get_student_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessment = _get_published_assessment(assessment_id, db)

    attempt_complete = _get_completed_session(assessment_id, current_user.id, db) is not None

    # If not running, return only metadata with no items. Once staff have stopped the
    # assessment, a student who submitted may see their overall score (results released).
    if not assessment.is_running:
        weighted_score = (
            assessment_scoring.compute_weighted_score(db, assessment, current_user.id)
            if attempt_complete
            else None
        )
        return StudentAssessmentDetail(
            id=assessment.id,
            title=assessment.title,
            description=assessment.description,
            is_running=False,
            has_password=bool(assessment.password),
            time_limit_minutes=assessment.time_limit_minutes,
            attempt_complete=attempt_complete,
            weighted_score=weighted_score,
            items=[],
        )

    # If running, build items with visited flags.
    session = _get_active_session(assessment_id, current_user.id, db)

    visited_ids: set[int] = set()
    if session:
        visits = (
            db.query(AssessmentItemVisit.assessment_item_id)
            .filter(AssessmentItemVisit.session_id == session.id)
            .all()
        )
        visited_ids = {v[0] for v in visits}

    # The item list + resolved titles are identical for every student and frozen for
    # the run's duration, so cache them under assessment_body:{id} (invalidated on any
    # Assessment/AssessmentItem change). At exam start this is the heaviest read in the
    # app hit by the whole cohort at once; caching + single-flight collapses it to one
    # rebuild. Only the per-student `visited` overlay stays live.
    def produce_body() -> list[StudentAssessmentItemView]:
        return [_build_item_view(item, False, db) for item in assessment.items]

    body_items = cache_read(
        db, assessment_body_ns(assessment_id), key=("body",), producer=produce_body
    )

    # Overlay this student's visited flags; model_copy avoids mutating the shared
    # cached instances.
    items = [
        iv.model_copy(update={"visited": True}) if iv.id in visited_ids else iv
        for iv in body_items
    ]

    return StudentAssessmentDetail(
        id=assessment.id,
        title=assessment.title,
        description=assessment.description,
        is_running=True,
        has_password=bool(assessment.password),
        time_limit_minutes=assessment.time_limit_minutes,
        attempt_complete=attempt_complete,
        items=items,
    )


@router.post("/{assessment_id}/join", response_model=AssessmentSessionResponse)
def join_assessment(
    assessment_id: int,
    body: JoinRequest = Body(default=JoinRequest()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessment = _get_published_assessment(assessment_id, db)

    if not assessment.is_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assessment has not been started by staff",
        )

    # Single-attempt: if the student already ended & submitted, block retaking.
    if _get_completed_session(assessment_id, current_user.id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You have already submitted this assessment and cannot retake it.",
        )

    # Return existing active session if already joined (skip password check)
    existing = _get_active_session(assessment_id, current_user.id, db)
    if existing:
        return AssessmentSessionResponse(
            id=existing.id,
            assessment_id=existing.assessment_id,
            user_id=existing.user_id,
            is_active=bool(existing.is_active),
            joined_at=existing.joined_at,
            submitted_at=existing.submitted_at,
            end_time=existing.end_time,
        )

    if assessment.password:
        if not body.password or body.password != assessment.password:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Incorrect assessment password",
            )

    from datetime import datetime, timedelta, timezone
    end_time = None
    if assessment.time_limit_minutes:
        end_time = datetime.now(timezone.utc) + timedelta(minutes=assessment.time_limit_minutes)

    session = AssessmentSession(
        assessment_id=assessment_id,
        user_id=current_user.id,
        end_time=end_time,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return AssessmentSessionResponse(
        id=session.id,
        assessment_id=session.assessment_id,
        user_id=session.user_id,
        is_active=bool(session.is_active),
        joined_at=session.joined_at,
        submitted_at=session.submitted_at,
        end_time=session.end_time,
    )


@router.get("/{assessment_id}/session", response_model=AssessmentSessionResponse)
def get_session(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_published_assessment(assessment_id, db)

    session = _get_active_session(assessment_id, current_user.id, db)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active session found")

    return AssessmentSessionResponse(
        id=session.id,
        assessment_id=session.assessment_id,
        user_id=session.user_id,
        is_active=bool(session.is_active),
        joined_at=session.joined_at,
        submitted_at=session.submitted_at,
        end_time=session.end_time,
    )


@router.post("/{assessment_id}/session/visit-item/{assessment_item_id}", response_model=ItemVisitResponse)
def visit_item(
    assessment_id: int,
    assessment_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_published_assessment(assessment_id, db)

    session = _get_active_session(assessment_id, current_user.id, db)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active session. Join the assessment first.",
        )

    # Verify the item belongs to this assessment
    item = (
        db.query(AssessmentItem)
        .filter(
            AssessmentItem.id == assessment_item_id,
            AssessmentItem.assessment_id == assessment_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment item not found")

    # Get-or-create visit (idempotent)
    visit = (
        db.query(AssessmentItemVisit)
        .filter(
            AssessmentItemVisit.session_id == session.id,
            AssessmentItemVisit.assessment_item_id == assessment_item_id,
        )
        .first()
    )
    if not visit:
        visit = AssessmentItemVisit(
            session_id=session.id,
            assessment_item_id=assessment_item_id,
        )
        db.add(visit)
        db.commit()
        db.refresh(visit)

    return ItemVisitResponse(
        session_id=visit.session_id,
        assessment_item_id=visit.assessment_item_id,
        first_visited_at=visit.first_visited_at,
    )


@router.post("/{assessment_id}/session/submit", response_model=AssessmentSessionResponse)
def submit_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_published_assessment(assessment_id, db)

    session = _get_active_session(assessment_id, current_user.id, db)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active session to submit",
        )

    finalize_session(db, session)
    db.refresh(session)

    return AssessmentSessionResponse(
        id=session.id,
        assessment_id=session.assessment_id,
        user_id=session.user_id,
        is_active=bool(session.is_active),
        joined_at=session.joined_at,
        submitted_at=session.submitted_at,
        end_time=session.end_time,
    )
