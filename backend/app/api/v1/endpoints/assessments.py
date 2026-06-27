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
        item_title=_resolve_item_title(item, db),
    )


def _replace_items(assessment: Assessment, items_in, db: Session) -> None:
    """Delete existing items and insert the new ordered list."""
    db.query(AssessmentItem).filter(
        AssessmentItem.assessment_id == assessment.id
    ).delete(synchronize_session=False)

    for idx, item_data in enumerate(items_in):
        db.add(AssessmentItem(
            assessment_id=assessment.id,
            item_type=item_data.item_type,
            item_id=item_data.item_id,
            order_index=item_data.order_index if item_data.order_index is not None else idx,
        ))


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
    )
    db.add(assessment)
    db.flush()

    for idx, item_data in enumerate(data.items):
        db.add(AssessmentItem(
            assessment_id=assessment.id,
            item_type=item_data.item_type,
            item_id=item_data.item_id,
            order_index=item_data.order_index if item_data.order_index is not None else idx,
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
        created_at=assessment.created_at,
        updated_at=assessment.updated_at,
    )


@router.get("", response_model=List[AssessmentListItem])
def list_assessments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    assessments = (
        db.query(Assessment)
        .filter(Assessment.is_deleted == 0)
        .order_by(Assessment.created_at.desc())
        .all()
    )
    return [
        AssessmentListItem(
            id=a.id,
            title=a.title,
            description=a.description,
            is_published=bool(a.is_published),
            is_running=bool(a.is_running),
            item_count=len(a.items),
            has_password=bool(a.password),
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in assessments
    ]


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

    assessment.is_published = 1
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

    if assessment.is_running:
        assessment.is_running = 0

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

    assessment.is_running = 0
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
        db.query(AssessmentSession, User.email)
        .join(User, AssessmentSession.user_id == User.id)
        .filter(AssessmentSession.assessment_id == assessment_id)
        .order_by(AssessmentSession.joined_at.desc())
        .all()
    )

    # Keep only the most recent session per student (descending joined_at guarantees first seen = latest)
    seen: dict = {}
    for session, email in rows:
        if session.user_id not in seen:
            seen[session.user_id] = (session, email)

    students = [
        AssessmentStudentRow(
            user_id=session.user_id,
            email=email,
            is_active=bool(session.is_active),
            joined_at=session.joined_at,
            submitted_at=session.submitted_at,
        )
        for session, email in seen.values()
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

    for item in items:
        title = _resolve_item_title(item, db)
        score = AssessmentItemComponentScore(
            assessment_item_id=item.id,
            item_type=item.item_type,
            item_id=item.item_id,
            item_title=title,
            order_index=item.order_index,
        )

        if item.item_type == "sql_question":
            attempts = (
                db.query(Attempt)
                .filter(Attempt.user_id == student_id, Attempt.question_id == item.item_id)
                .all()
            )
            score.attempt_count = len(attempts)
            score.has_correct_attempt = any(bool(a.is_correct) for a in attempts)

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

        component_scores.append(score)

    return StudentComponentScoresResponse(
        student_id=student_id,
        student_email=student.email,
        assessment_id=assessment.id,
        assessment_title=assessment.title,
        items=component_scores,
    )
