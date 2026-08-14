from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.models.assessment_class_window import AssessmentClassWindow
from app.models.whitelist import WhitelistEntry
from app.models.question import Question
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.lab import Lab
from app.schemas.assessment import (
    AssessmentCreate,
    AssessmentUpdate,
    AssessmentListItem,
    AssessmentResponse,
    AssessmentItemResponse,
    AssessmentStudentsResponse,
    AssessmentStudentRow,
    StudentComponentScoresResponse,
    AssessmentItemComponentScore,
    AssessmentItemAnalyticsResponse,
    AssessmentAnalyticsSummaryRow,
    AssessmentAnalyticsSummaryResponse,
    GatewayConfigUpdate,
    GatewayConfigResponse,
    ClassWindowOut,
)
from app.dependencies import get_current_user, require_staff_role
from app.services import (
    assessment_clone,
    assessment_registration,
    assessment_reset,
    assessment_scoring,
)
from app.core.cache import cache_read, bump_version, assessment_body_ns, Ns
from sqlalchemy import func

router = APIRouter(prefix="/assessments", tags=["assessments"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_item_title(item: AssessmentItem, db: Session) -> str:
    """Look up the display title for a polymorphic assessment item."""
    if item.item_type == "sql_question":
        row = db.query(Question.title).filter(Question.id == item.item_id).first()
        return row[0] if row else f"Question #{item.item_id}"
    if item.item_type == "er_question":
        row = db.query(ERDiagramQuestion.title).filter(ERDiagramQuestion.id == item.item_id).first()
        return row[0] if row else f"ER Question #{item.item_id}"
    if item.item_type in ("sql_lab", "graph_lab"):
        row = db.query(Lab.title).filter(Lab.id == item.item_id, Lab.is_deleted == 0).first()
        return row[0] if row else f"Lab #{item.item_id}"
    return f"Item #{item.item_id}"


def _build_item_response(item: AssessmentItem, db: Session) -> AssessmentItemResponse:
    return AssessmentItemResponse(
        id=item.id,
        item_type=item.item_type,
        item_id=item.item_id,
        order_index=item.order_index,
        weight=item.weight,
        hide_correctness=bool(item.hide_correctness),
        max_queries=item.max_queries,
        item_title=_resolve_item_title(item, db),
    )


def _equal_weights(n: int) -> List[int]:
    """Integer percentages summing to 100, remainder given to the earliest items.
    n=1 -> [100], n=3 -> [34, 33, 33], n=4 -> [25, 25, 25, 25]."""
    if n <= 0:
        return []
    base = 100 // n
    remainder = 100 - base * n
    return [base + 1 if i < remainder else base for i in range(n)]


def _resolve_weights(items_in) -> List[int]:
    """Return the weight to persist for each item. If every incoming weight is 0
    (legacy/unweighted), auto-distribute equally; otherwise honour the given weights."""
    if items_in and all((item.weight or 0) == 0 for item in items_in):
        return _equal_weights(len(items_in))
    return [item.weight for item in items_in]


def _replace_items(assessment: Assessment, items_in, db: Session) -> None:
    """Delete existing items and insert the new ordered list."""
    db.query(AssessmentItem).filter(
        AssessmentItem.assessment_id == assessment.id
    ).delete(synchronize_session=False)

    weights = _resolve_weights(items_in)
    for idx, item_data in enumerate(items_in):
        db.add(AssessmentItem(
            assessment_id=assessment.id,
            item_type=item_data.item_type,
            item_id=item_data.item_id,
            order_index=item_data.order_index if item_data.order_index is not None else idx,
            weight=weights[idx],
            hide_correctness=1 if item_data.hide_correctness else 0,
            max_queries=item_data.max_queries,
        ))

    # The bulk delete above bypasses the ORM unit of work, so the after_flush
    # auto-invalidation listener won't see it. The ORM inserts below normally do
    # trigger it, but not when items_in is empty — bump explicitly to cover that.
    bump_version(db, Ns.ASSESSMENTS)
    bump_version(db, assessment_body_ns(assessment.id))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("", response_model=AssessmentResponse, status_code=status.HTTP_201_CREATED)
def create_assessment(
    data: AssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = Assessment(
        title=data.title,
        description=data.description,
        created_by=current_user.id,
        is_published=0,
        is_running=0,
        is_deleted=0,
        password=data.password or None,
        time_limit_minutes=data.time_limit_minutes,
    )
    db.add(assessment)
    db.flush()

    weights = _resolve_weights(data.items)
    for idx, item_data in enumerate(data.items):
        db.add(AssessmentItem(
            assessment_id=assessment.id,
            item_type=item_data.item_type,
            item_id=item_data.item_id,
            order_index=item_data.order_index if item_data.order_index is not None else idx,
            weight=weights[idx],
            hide_correctness=1 if item_data.hide_correctness else 0,
            max_queries=item_data.max_queries,
        ))

    db.commit()
    db.refresh(assessment)

    return AssessmentResponse(
        id=assessment.id,
        title=assessment.title,
        description=assessment.description,
        is_published=bool(assessment.is_published),
        is_running=bool(assessment.is_running),
        items=[_build_item_response(i, db) for i in assessment.items],
        created_by=assessment.created_by,
        password=assessment.password,
        has_password=bool(assessment.password),
        time_limit_minutes=assessment.time_limit_minutes,
        gateway_enabled=bool(assessment.gateway_enabled),
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.get("", response_model=List[AssessmentListItem])
def list_assessments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    # Staff-only and identical across all staff/admin, so cached in-process and
    # invalidated on any Assessment/AssessmentItem mutation (see app/core/cache.py).
    def producer():
        assessments = (
            db.query(Assessment)
            .filter(Assessment.is_deleted == 0)
            .order_by(Assessment.created_at.desc())
            .all()
        )
        # One grouped COUNT instead of a per-row len(a.items) lazy load (avoids N+1).
        counts = dict(
            db.query(AssessmentItem.assessment_id, func.count(AssessmentItem.id))
            .group_by(AssessmentItem.assessment_id)
            .all()
        )
        return [
            AssessmentListItem(
                id=a.id,
                title=a.title,
                description=a.description,
                is_published=bool(a.is_published),
                is_running=bool(a.is_running),
                item_count=counts.get(a.id, 0),
                has_password=bool(a.password),
                time_limit_minutes=a.time_limit_minutes,
                gateway_enabled=bool(a.gateway_enabled),
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in assessments
        ]

    return cache_read(db, Ns.ASSESSMENTS, key=("staff",), producer=producer)


@router.get("/class-groups", response_model=List[str])
def list_all_class_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Class groups available for Timing-Gateway windows, not scoped to an assessment.

    Lets the editor list groups before the assessment has been created and given an id.
    Declared ahead of ``/{assessment_id}`` so it isn't captured by that dynamic route."""
    return _distinct_class_groups(db)


@router.get("/analytics/summary", response_model=AssessmentAnalyticsSummaryResponse)
def get_assessment_analytics_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """One row per assessment for the admin dashboard's Assessments tab, plus the
    platform-wide registered/signed-in counts its Overview tab shows.

    Declared ahead of ``/{assessment_id}`` so that dynamic route does not capture
    "analytics" as an id — the same ordering constraint ``/class-groups`` documents.

    Each row's average and started count come from the materialized per-assessment
    analytics, so this is a cache read per assessment rather than a fresh aggregate."""
    assessments = (
        db.query(Assessment)
        .filter(Assessment.is_deleted == 0)
        .order_by(Assessment.id.desc())
        .all()
    )

    item_counts = dict(
        db.query(AssessmentItem.assessment_id, func.count(AssessmentItem.id))
        .group_by(AssessmentItem.assessment_id)
        .all()
    )

    rows: List[AssessmentAnalyticsSummaryRow] = []
    for assessment in assessments:
        analytics = assessment_scoring.get_or_compute_analytics(db, assessment, None)
        scope_groups = assessment_registration.assessment_class_groups(db, assessment)
        rows.append(AssessmentAnalyticsSummaryRow(
            assessment_id=assessment.id,
            title=assessment.title,
            is_published=bool(assessment.is_published),
            question_count=item_counts.get(assessment.id, 0),
            registered_count=assessment_registration.registered_count(db, scope_groups),
            started_count=analytics.student_count,
            avg_weighted_score=analytics.avg_weighted_score,
        ))

    return AssessmentAnalyticsSummaryResponse(
        platform_registered=assessment_registration.registered_count(db, None),
        platform_signed_in=assessment_registration.signed_in_student_count(db),
        assessments=rows,
    )


@router.get("/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()

    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    return AssessmentResponse(
        id=assessment.id,
        title=assessment.title,
        description=assessment.description,
        is_published=bool(assessment.is_published),
        is_running=bool(assessment.is_running),
        items=[_build_item_response(i, db) for i in assessment.items],
        created_by=assessment.created_by,
        password=assessment.password,
        has_password=bool(assessment.password),
        time_limit_minutes=assessment.time_limit_minutes,
        gateway_enabled=bool(assessment.gateway_enabled),
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.put("/{assessment_id}", response_model=AssessmentResponse)
def update_assessment(
    assessment_id: int,
    data: AssessmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()

    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.is_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit assessment while it is running. Stop it first.",
        )

    # A published assessment is frozen (its items point to content clones). Editing the
    # item list would orphan those clones, so require unpublish first. Metadata edits are
    # still allowed below.
    if data.items is not None and assessment.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit assessment items while it is published. Unpublish first.",
        )

    if data.title is not None:
        assessment.title = data.title
    if data.description is not None:
        assessment.description = data.description
    if data.items is not None:
        _replace_items(assessment, data.items, db)

    if data.clear_password:
        assessment.password = None
    elif data.password:
        assessment.password = data.password

    if data.clear_time_limit:
        assessment.time_limit_minutes = None
    elif data.time_limit_minutes is not None:
        assessment.time_limit_minutes = data.time_limit_minutes

    assessment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(assessment)

    return AssessmentResponse(
        id=assessment.id,
        title=assessment.title,
        description=assessment.description,
        is_published=bool(assessment.is_published),
        is_running=bool(assessment.is_running),
        items=[_build_item_response(i, db) for i in assessment.items],
        created_by=assessment.created_by,
        password=assessment.password,
        has_password=bool(assessment.password),
        time_limit_minutes=assessment.time_limit_minutes,
        gateway_enabled=bool(assessment.gateway_enabled),
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.delete("/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()

    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.is_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete assessment while it is running. Stop it first.",
        )

    # Reclaim clone SQLite files and soft-delete clone rows before removing the assessment.
    assessment_clone.delete_cloned_content(db, assessment.id)

    assessment.is_deleted = 1
    assessment.updated_at = datetime.utcnow()
    db.commit()
    return None


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

@router.post("/{assessment_id}/publish", response_model=AssessmentListItem)
def publish_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()

    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    # Freeze the assessment: deep-copy each item's content into an assessment-owned clone
    # and repoint item_id to the clone, so student progress/attempts on this assessment are
    # isolated from the master bank and other assessments. Idempotent: items already frozen
    # (source_item_id set) are skipped, so re-publishing does not double-clone.
    try:
        for item in assessment.items:
            if item.source_item_id is not None:
                continue
            clone_id = assessment_clone.clone_item(db, item, assessment.id)
            item.source_item_id = item.item_id
            item.item_id = clone_id

        assessment.is_published = 1
        assessment.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(assessment)
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to publish assessment: {exc}",
        )

    return AssessmentListItem(
        id=assessment.id,
        title=assessment.title,
        description=assessment.description,
        is_published=bool(assessment.is_published),
        is_running=bool(assessment.is_running),
        item_count=len(assessment.items),
        has_password=bool(assessment.password),
        time_limit_minutes=assessment.time_limit_minutes,
        gateway_enabled=bool(assessment.gateway_enabled),
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.post("/{assessment_id}/unpublish", response_model=AssessmentListItem)
def unpublish_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()

    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if assessment.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Published assessments cannot be unpublished.",
        )

    if assessment.is_running:
        assessment.is_running = 0

    # Tear down the frozen clones (delete SQLite files, soft-delete rows) and restore each
    # item's pointer to its master content so the assessment becomes editable again.
    assessment_clone.delete_cloned_content(db, assessment.id)
    for item in assessment.items:
        if item.source_item_id is not None:
            item.item_id = item.source_item_id
            item.source_item_id = None

    assessment.is_published = 0
    assessment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(assessment)

    return AssessmentListItem(
        id=assessment.id,
        title=assessment.title,
        description=assessment.description,
        is_published=bool(assessment.is_published),
        is_running=bool(assessment.is_running),
        item_count=len(assessment.items),
        has_password=bool(assessment.password),
        time_limit_minutes=assessment.time_limit_minutes,
        gateway_enabled=bool(assessment.gateway_enabled),
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.post("/{assessment_id}/start", response_model=AssessmentListItem)
def start_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()

    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    if not assessment.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assessment must be published before starting.",
        )

    assessment.is_running = 1
    assessment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(assessment)

    return AssessmentListItem(
        id=assessment.id,
        title=assessment.title,
        description=assessment.description,
        is_published=bool(assessment.is_published),
        is_running=bool(assessment.is_running),
        item_count=len(assessment.items),
        has_password=bool(assessment.password),
        time_limit_minutes=assessment.time_limit_minutes,
        gateway_enabled=bool(assessment.gateway_enabled),
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.post("/{assessment_id}/stop", response_model=AssessmentListItem)
def stop_assessment(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()

    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    assessment.is_running = 0  # blocks new joins / hides items on reload (unchanged)
    assessment.updated_at = datetime.utcnow()
    # Force-end & submit everyone still active, regardless of their remaining time. Sets the
    # same end-state as finalize_session (is_active=0, attempt_complete=1, submitted_at). The
    # is_active==1 filter makes this idempotent and covers untimed attempts (end_time NULL) too.
    db.query(AssessmentSession).filter(
        AssessmentSession.assessment_id == assessment_id,
        AssessmentSession.is_active == 1,
    ).update(
        {"is_active": 0, "attempt_complete": 1, "submitted_at": datetime.utcnow()},
        synchronize_session=False,
    )
    # Bulk update() bypasses the ORM unit of work, so the after_flush auto-invalidation
    # won't see the roster change — bump the analytics namespace explicitly.
    bump_version(db, Ns.ASSESSMENT_ANALYTICS)
    db.commit()
    db.refresh(assessment)

    # Results are frozen the moment the assessment stops, so compute + persist the
    # cohort and per-class-group analytics right now instead of leaving them to be
    # computed lazily by whichever student or staff member opens a report first.
    # Runs after the commit above so it reads the final, committed roster/version.
    assessment_scoring.warm_analytics_cache(db, assessment)

    return AssessmentListItem(
        id=assessment.id,
        title=assessment.title,
        description=assessment.description,
        is_published=bool(assessment.is_published),
        is_running=bool(assessment.is_running),
        item_count=len(assessment.items),
        has_password=bool(assessment.password),
        time_limit_minutes=assessment.time_limit_minutes,
        gateway_enabled=bool(assessment.gateway_enabled),
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


# ---------------------------------------------------------------------------
# Timing Gateway (per-class-group access windows)
# ---------------------------------------------------------------------------

def _window_status(window: AssessmentClassWindow) -> str:
    """Lifecycle of a window relative to server time: upcoming | active | completed."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    start = window.start_at if window.start_at.tzinfo else window.start_at.replace(tzinfo=timezone.utc)
    end = window.end_at if window.end_at.tzinfo else window.end_at.replace(tzinfo=timezone.utc)
    if now < start:
        return "upcoming"
    if now >= end:
        return "completed"
    return "active"


def _active_session_counts(db: Session, assessment_id: int) -> dict:
    """Map class_group -> number of active (mid-attempt) sessions in this assessment."""
    rows = (
        db.query(User.class_group, func.count(AssessmentSession.id))
        .join(AssessmentSession, AssessmentSession.user_id == User.id)
        .filter(
            AssessmentSession.assessment_id == assessment_id,
            AssessmentSession.is_active == 1,
        )
        .group_by(User.class_group)
        .all()
    )
    return {cg: cnt for cg, cnt in rows}


def _to_class_window_out(window: AssessmentClassWindow, active_counts: dict) -> ClassWindowOut:
    # Normalize to timezone-aware UTC before serializing — see student_assessments.py's
    # _session_response for why a naive datetime here is dangerous (the frontend parses a
    # timezone-less ISO string as local time, silently shifting the displayed window).
    from app.services.assessment_gateway import as_utc

    return ClassWindowOut(
        id=window.id,
        class_group=window.class_group,
        start_at=as_utc(window.start_at),
        end_at=as_utc(window.end_at),
        is_enabled=bool(window.is_enabled),
        status=_window_status(window),
        active_session_count=active_counts.get(window.class_group, 0),
    )


def _get_staff_assessment(assessment_id: int, db: Session) -> Assessment:
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return assessment


def _distinct_class_groups(db: Session) -> List[str]:
    """Distinct class-group names available to configure windows for.

    Sourced from both registered users and the pre-registration whitelist so staff can
    schedule a group before its students have logged in."""
    user_groups = db.query(User.class_group).filter(User.class_group.isnot(None)).distinct().all()
    wl_groups = (
        db.query(WhitelistEntry.class_group)
        .filter(WhitelistEntry.class_group.isnot(None))
        .distinct()
        .all()
    )
    groups = {g[0] for g in user_groups} | {g[0] for g in wl_groups}
    return sorted(g for g in groups if g)


@router.get("/{assessment_id}/class-groups", response_model=List[str])
def list_assessment_class_groups(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    _get_staff_assessment(assessment_id, db)
    return _distinct_class_groups(db)


@router.get("/{assessment_id}/windows", response_model=GatewayConfigResponse)
def get_gateway_config(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = _get_staff_assessment(assessment_id, db)
    windows = (
        db.query(AssessmentClassWindow)
        .filter(AssessmentClassWindow.assessment_id == assessment_id)
        .order_by(AssessmentClassWindow.start_at)
        .all()
    )
    active_counts = _active_session_counts(db, assessment_id)
    return GatewayConfigResponse(
        assessment_id=assessment_id,
        gateway_enabled=bool(assessment.gateway_enabled),
        windows=[_to_class_window_out(w, active_counts) for w in windows],
    )


@router.put("/{assessment_id}/windows", response_model=GatewayConfigResponse)
def update_gateway_config(
    assessment_id: int,
    payload: GatewayConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Replace the assessment's Timing-Gateway configuration (toggle + all windows).

    Windows are validated (end after start, one per group) by the schema. Editing a
    window whose group has students mid-attempt reconciles those sessions' hard_deadline
    to the new window end and surfaces a warning (requirement #8)."""
    assessment = _get_staff_assessment(assessment_id, db)
    warnings: List[str] = []

    # Replace the full window set.
    db.query(AssessmentClassWindow).filter(
        AssessmentClassWindow.assessment_id == assessment_id
    ).delete(synchronize_session=False)
    for w in payload.windows:
        db.add(AssessmentClassWindow(
            assessment_id=assessment_id,
            class_group=w.class_group,
            start_at=w.start_at,
            end_at=w.end_at,
            is_enabled=1 if w.is_enabled else 0,
        ))

    assessment.gateway_enabled = 1 if payload.gateway_enabled else 0
    assessment.updated_at = datetime.utcnow()
    db.flush()

    # Reconcile active sessions' hard_deadline to the (possibly new) window ends so an
    # edit before/while the assessment runs takes effect immediately for those students.
    enabled_window_end = {
        w.class_group: w.end_at for w in payload.windows if w.is_enabled
    }
    active_rows = (
        db.query(AssessmentSession, User.class_group)
        .join(User, User.id == AssessmentSession.user_id)
        .filter(
            AssessmentSession.assessment_id == assessment_id,
            AssessmentSession.is_active == 1,
        )
        .all()
    )
    changed = 0
    for sess, cg in active_rows:
        new_hd = enabled_window_end.get(cg) if payload.gateway_enabled else None
        if sess.hard_deadline != new_hd:
            sess.hard_deadline = new_hd
            changed += 1
    if changed:
        warnings.append(
            f"{changed} student(s) with an in-progress attempt had their deadline updated "
            f"to match the new window."
        )

    # gateway_enabled feeds the cached staff list.
    bump_version(db, Ns.ASSESSMENTS)
    db.commit()

    windows = (
        db.query(AssessmentClassWindow)
        .filter(AssessmentClassWindow.assessment_id == assessment_id)
        .order_by(AssessmentClassWindow.start_at)
        .all()
    )
    active_counts = _active_session_counts(db, assessment_id)
    return GatewayConfigResponse(
        assessment_id=assessment_id,
        gateway_enabled=bool(assessment.gateway_enabled),
        windows=[_to_class_window_out(w, active_counts) for w in windows],
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Student activity (staff view)
# ---------------------------------------------------------------------------

def _student_roster(db: Session, assessment_id: int, class_group: Optional[str] = None):
    """Most-recent AssessmentSession per student who has joined this assessment.

    Returns a list of (session, email, class_group) tuples, optionally restricted to a
    single class_group. Shared by the student list and the item-analytics aggregate so
    both agree on exactly who counts as "the roster".
    """
    query = (
        db.query(AssessmentSession, User.email, User.class_group)
        .join(User, AssessmentSession.user_id == User.id)
        .filter(AssessmentSession.assessment_id == assessment_id)
    )
    if class_group:
        query = query.filter(User.class_group == class_group)
    rows = query.order_by(AssessmentSession.joined_at.desc()).all()

    # Keep only the most recent session per student (descending joined_at guarantees first seen = latest)
    seen: dict = {}
    for session, email, cg in rows:
        if session.user_id not in seen:
            seen[session.user_id] = (session, email, cg)
    return list(seen.values())


@router.get("/{assessment_id}/students", response_model=AssessmentStudentsResponse)
def list_assessment_students(
    assessment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = _get_staff_assessment(assessment_id, db)

    roster = _student_roster(db, assessment_id)
    # Read every student's weighted total from the shared, cached cohort analytics
    # instead of recomputing per student (was O(students × items) queries).
    scores = assessment_scoring.get_or_compute_analytics(
        db, assessment, class_group=None
    ).per_student_scores
    students = [
        AssessmentStudentRow(
            user_id=session.user_id,
            email=email,
            class_group=class_group,
            is_active=bool(session.is_active),
            joined_at=session.joined_at,
            submitted_at=session.submitted_at,
            weighted_score=scores.get(session.user_id),
        )
        for session, email, class_group in roster
    ]

    return AssessmentStudentsResponse(
        assessment_id=assessment.id,
        assessment_title=assessment.title,
        students=students,
    )


@router.get("/{assessment_id}/item-analytics", response_model=AssessmentItemAnalyticsResponse)
def get_assessment_item_analytics(
    assessment_id: int,
    class_group: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Per-question average score (and, for labs, average tasks completed) across a
    roster of students — the whole cohort, or a single class_group when provided.

    Reads the shared, cached analytics (compute-once, materialized in
    assessment_analytics) instead of the per-(student × item) query fan-out.
    `registered_count` is computed live rather than read from that cache, so editing the
    whitelist moves the denominator immediately."""
    assessment = _get_staff_assessment(assessment_id, db)

    analytics = assessment_scoring.get_or_compute_analytics(db, assessment, class_group)

    # Selecting a group narrows the denominator to that group; otherwise it is whoever the
    # gateway admits (everyone, when the gateway is off).
    scope_groups = (
        [class_group] if class_group
        else assessment_registration.assessment_class_groups(db, assessment)
    )

    return AssessmentItemAnalyticsResponse(
        assessment_id=assessment.id,
        assessment_title=assessment.title,
        class_group=class_group,
        student_count=analytics.student_count,
        registered_count=assessment_registration.registered_count(db, scope_groups),
        avg_weighted_score=analytics.avg_weighted_score,
        items=analytics.items,
    )


@router.get("/{assessment_id}/students/{student_id}/component-scores", response_model=StudentComponentScoresResponse)
def get_student_component_scores(
    assessment_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    student = db.query(User).filter(User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Get the student's session for visit lookups
    session = (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.assessment_id == assessment_id,
            AssessmentSession.user_id == student_id,
        )
        .first()
    )

    items = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.assessment_id == assessment_id)
        .order_by(AssessmentItem.order_index)
        .all()
    )

    component_scores: List[AssessmentItemComponentScore] = []
    total_weight = 0
    earned_weight = 0.0

    for item in items:
        title = _resolve_item_title(item, db)
        detail = assessment_scoring.item_score_detail(
            db, item, student_id, session_id=session.id if session else None
        )

        score = AssessmentItemComponentScore(
            assessment_item_id=item.id,
            item_type=item.item_type,
            item_id=item.item_id,
            item_title=title,
            order_index=item.order_index,
            weight=item.weight,
            has_correct_attempt=detail.has_correct_attempt,
            attempt_count=detail.attempt_count,
            tasks_correct=detail.tasks_correct,
            tasks_total=detail.tasks_total,
            visited=detail.visited,
            score_fraction=round(detail.fraction, 4),
            weighted_points=round(item.weight * detail.fraction, 2),
        )
        total_weight += item.weight
        earned_weight += item.weight * detail.fraction

        component_scores.append(score)

    total_weighted_score = (
        round(earned_weight / total_weight * 100, 1) if total_weight > 0 else None
    )

    return StudentComponentScoresResponse(
        student_id=student_id,
        student_email=student.email,
        assessment_id=assessment.id,
        assessment_title=assessment.title,
        items=component_scores,
        total_weighted_score=total_weighted_score,
    )


@router.post("/{assessment_id}/students/{student_id}/reset")
def reset_student_attempt(
    assessment_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Erase a student's attempt data for this assessment and clear their completion lock,
    giving them a clean slate to retake it."""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.is_deleted == 0,
    ).first()
    if not assessment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")

    student = db.query(User).filter(User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Reset is only safe while published: item_id points to assessment-private clones. If
    # unpublished, item_id reverts to master content and a purge would wipe practice data.
    if not assessment.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Publish the assessment before resetting a student's attempt.",
        )

    summary = assessment_reset.reset_student_attempt(db, assessment, student_id)
    db.commit()
    return {"detail": "Attempt reset", "student_id": student_id, "deleted": summary}
