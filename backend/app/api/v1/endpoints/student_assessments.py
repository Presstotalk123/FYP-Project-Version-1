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
from app.services import assessment_gateway
from app.services.assessment_gateway import GatewayState, effective_deadline, as_utc
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


def _maybe_finalize_expired(db: Session, session: AssessmentSession | None) -> None:
    """Opportunistic (non-raising) expiration sweep for a single session.

    The request-driven half of the lazy design: whenever we already hold a session we
    finalize it if it is active and past its effective deadline (personal timer or the
    class-group window cap). Unlike ``enforce_not_expired`` this does not raise — it is
    used on read paths (detail/list) so an idle/disconnected student's lingering session
    gets force-submitted the next time anyone touches it, with no background job."""
    from datetime import datetime, timezone

    if session is None or not session.is_active:
        return
    deadline = effective_deadline(session)
    if deadline is not None and datetime.now(timezone.utc) >= deadline:
        finalize_session(db, session)


def _session_response(session: AssessmentSession) -> AssessmentSessionResponse:
    # Defense in depth: normalize every deadline-bearing timestamp to timezone-aware UTC
    # before it leaves the API, regardless of what the DB column happens to return. A
    # naive datetime serializes with no UTC offset; the frontend's `new Date(iso)` then
    # parses it as *local browser time*, silently shifting the deadline by the viewer's
    # UTC offset (e.g. 8h early in Singapore) and triggering an immediate spurious
    # auto-submit. This bit us once already (a migration created hard_deadline as
    # TIMESTAMP instead of TIMESTAMPTZ) — normalizing here means a future column-type
    # mistake fails safe instead of silently corrupting every student's deadline.
    return AssessmentSessionResponse(
        id=session.id,
        assessment_id=session.assessment_id,
        user_id=session.user_id,
        is_active=bool(session.is_active),
        joined_at=session.joined_at,
        submitted_at=session.submitted_at,
        end_time=as_utc(session.end_time),
        hard_deadline=as_utc(session.hard_deadline),
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
        # Opportunistically finalize this student's lingering session if its window/timer
        # has elapsed, so the dashboard reflects reality without a background job.
        _maybe_finalize_expired(db, _get_active_session(a.id, current_user.id, db))

        # Per-user attempt state. The completed session (if any) carries the submission
        # time; the weighted score is only surfaced once results are released.
        completed = _get_completed_session(a.id, current_user.id, db)
        attempt_complete = completed is not None

        # Effective "live for this student": when the gateway is on, the class-group
        # window's OPEN state supersedes the manual is_running flag, and results release
        # once the window has CLOSED (mirroring the non-gateway "stopped" release).
        if a.gateway_enabled:
            state = assessment_gateway.resolve_state(db, a, current_user).state
            is_live = state == GatewayState.OPEN
            results_released = state == GatewayState.CLOSED
        else:
            is_live = bool(a.is_running)
            results_released = not a.is_running

        # Persisted at finalization (see assessment_timer.finalize_session); no live recompute.
        weighted_score = (
            completed.weighted_score
            if attempt_complete and results_released
            else None
        )
        items.append(
            StudentAssessmentListItem(
                id=a.id,
                title=a.title,
                description=a.description,
                is_running=is_live,
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

    # Resolve the Timing-Gateway state for this student's class group. When the gateway
    # is enabled, the window's OPEN state supersedes the manual is_running flag.
    resolved = assessment_gateway.resolve_state(db, assessment, current_user)
    gateway_fields = dict(
        gateway_enabled=bool(assessment.gateway_enabled),
        gateway_state=resolved.state.value if assessment.gateway_enabled else None,
        window_start=resolved.start_at,
        window_end=resolved.end_at,
    )
    is_open = resolved.is_open if assessment.gateway_enabled else bool(assessment.is_running)

    completed_session = _get_completed_session(assessment_id, current_user.id, db)
    attempt_complete = completed_session is not None

    # If not open for this student, return only metadata with no items. Once the assessment
    # is closed/stopped, a student who submitted may see their overall score (released).
    if not is_open:
        # Persisted at finalization (see assessment_timer.finalize_session); no live recompute.
        weighted_score = (
            completed_session.weighted_score if attempt_complete else None
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
            **gateway_fields,
        )

    # If open, build items with visited flags.
    session = _get_active_session(assessment_id, current_user.id, db)
    # Force-submit a lingering session whose deadline already passed (e.g. window shrank).
    _maybe_finalize_expired(db, session)
    if session is not None and not session.is_active:
        session = None

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
        **gateway_fields,
    )


@router.post("/{assessment_id}/join", response_model=AssessmentSessionResponse)
def join_assessment(
    assessment_id: int,
    body: JoinRequest = Body(default=JoinRequest()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    assessment = _get_published_assessment(assessment_id, db)

    # Timing Gateway: when enabled, the per-class-group window (not the manual
    # is_running flag) decides whether this student may join, and its end_at becomes
    # the session's immovable hard_deadline.
    hard_deadline = None
    if assessment.gateway_enabled:
        resolved = assessment_gateway.resolve_state(db, assessment, current_user)
        if resolved.state == GatewayState.NO_WINDOW:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access window is configured for your class group.",
            )
        if resolved.state == GatewayState.UPCOMING:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This assessment opens at {resolved.start_at.isoformat()}.",
            )
        if resolved.state == GatewayState.CLOSED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This assessment window has closed.",
            )
        # OPEN
        hard_deadline = resolved.end_at
    elif not assessment.is_running:
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
        return _session_response(existing)

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
        hard_deadline=hard_deadline,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return _session_response(session)


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

    return _session_response(session)


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

    return _session_response(session)
