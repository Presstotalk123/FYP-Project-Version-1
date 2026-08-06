from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.database import get_db
from app.models.user import User
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.models.assessment_item_visit import AssessmentItemVisit
from app.models.question import Question
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.lab import Lab
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.attempt import Attempt
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
)
from app.dependencies import get_current_user, require_staff_role
from app.services import assessment_clone, assessment_reset, assessment_scoring
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
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in assessments
        ]

    return cache_read(db, Ns.ASSESSMENTS, key=("staff",), producer=producer)


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
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


# ---------------------------------------------------------------------------
# Student activity (staff view)
# ---------------------------------------------------------------------------

@router.get("/{assessment_id}/students", response_model=AssessmentStudentsResponse)
def list_assessment_students(
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

    rows = (
        db.query(AssessmentSession, User.email, User.class_group)
        .join(User, AssessmentSession.user_id == User.id)
        .filter(AssessmentSession.assessment_id == assessment_id)
        .order_by(AssessmentSession.joined_at.desc())
        .all()
    )

    # Keep only the most recent session per student (descending joined_at guarantees first seen = latest)
    seen: dict = {}
    for session, email, class_group in rows:
        if session.user_id not in seen:
            seen[session.user_id] = (session, email, class_group)

    students = [
        AssessmentStudentRow(
            user_id=session.user_id,
            email=email,
            class_group=class_group,
            is_active=bool(session.is_active),
            joined_at=session.joined_at,
            submitted_at=session.submitted_at,
            weighted_score=assessment_scoring.compute_weighted_score(db, assessment, session.user_id),
        )
        for session, email, class_group in seen.values()
    ]

    return AssessmentStudentsResponse(
        assessment_id=assessment.id,
        assessment_title=assessment.title,
        students=students,
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
        score = AssessmentItemComponentScore(
            assessment_item_id=item.id,
            item_type=item.item_type,
            item_id=item.item_id,
            item_title=title,
            order_index=item.order_index,
            weight=item.weight,
        )

        # Correctness fraction (0.0-1.0), reusing the per-type data below where possible.
        fraction = 0.0

        if item.item_type == "sql_question":
            attempts = (
                db.query(Attempt)
                .filter(Attempt.user_id == student_id, Attempt.question_id == item.item_id)
                .all()
            )
            score.attempt_count = len(attempts)
            score.has_correct_attempt = any(bool(a.is_correct) for a in attempts)
            fraction = 1.0 if score.has_correct_attempt else 0.0

        elif item.item_type == "er_question":
            visited = False
            if session:
                visited = (
                    db.query(AssessmentItemVisit)
                    .filter(
                        AssessmentItemVisit.session_id == session.id,
                        AssessmentItemVisit.assessment_item_id == item.id,
                    )
                    .first()
                ) is not None
            score.visited = visited
            # ER grade comes from the LLM-graded ERD-tutor conversation (percent / 100).
            pct = assessment_scoring.er_percent(db, item.item_id, student_id)
            fraction = (pct / 100.0) if pct is not None else 0.0

        elif item.item_type in ("sql_lab", "graph_lab"):
            total_tasks = (
                db.query(LabTask)
                .filter(LabTask.lab_id == item.item_id, LabTask.is_deleted == 0)
                .count()
            )
            from sqlalchemy import func, case
            correct_count = (
                db.query(
                    func.count(func.distinct(
                        case((LabTaskSubmission.is_correct == 1, LabTaskSubmission.task_id))
                    ))
                )
                .filter(
                    LabTaskSubmission.user_id == student_id,
                    LabTaskSubmission.lab_id == item.item_id,
                )
                .scalar()
            ) or 0
            score.tasks_correct = correct_count
            score.tasks_total = total_tasks
            fraction = (correct_count / total_tasks) if total_tasks > 0 else 0.0

        score.score_fraction = round(fraction, 4)
        score.weighted_points = round(item.weight * fraction, 2)
        total_weight += item.weight
        earned_weight += item.weight * fraction

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
