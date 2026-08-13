"""Student report summaries.

Two views over the same completion data:
  - GET /student-report/summary            — the current student's own practice counts.
  - GET /student-report/students/{id}       — staff view: a student's practice counts
    plus a per-assessment score breakdown with cohort comparison.

Practice-count logic lives in app.services.student_report so both views agree.
Assessment scoring/roster/title helpers are reused from app.services.assessment_scoring.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.models.user import User
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.schemas.assessment import AssessmentItemComponentScore
from app.schemas.student_report import (
    StudentReportSummary,
    StudentReportAssessmentBlock,
    StudentFullReport,
)
from app.services import student_report as report_service
from app.services import assessment_scoring

router = APIRouter(prefix="/student-report", tags=["student-report"])


def _build_summary(db: Session, user_id: int) -> StudentReportSummary:
    sql_labs, graph_labs = report_service.labs_completed_by_type(db, user_id)
    return StudentReportSummary(
        sql_questions_completed=report_service.sql_questions_completed(db, user_id),
        erd_questions_completed=report_service.erd_questions_completed(db, user_id),
        sql_labs_completed=sql_labs,
        graph_labs_completed=graph_labs,
    )


@router.get("/summary", response_model=StudentReportSummary)
def get_student_report_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Practice-completion counts for the current student's report page."""
    return _build_summary(db, current_user.id)


def _assessment_block(
    db: Session,
    assessment: Assessment,
    session: AssessmentSession,
    student_id: int,
) -> StudentReportAssessmentBlock:
    """One submitted assessment: the student's per-item breakdown, their weighted
    total, and how it sits against the cohort average."""
    items = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.assessment_id == assessment.id)
        .order_by(AssessmentItem.order_index)
        .all()
    )

    component_scores = []
    for item in items:
        detail = assessment_scoring.item_score_detail(
            db, item, student_id, session_id=session.id
        )
        component_scores.append(
            AssessmentItemComponentScore(
                assessment_item_id=item.id,
                item_type=item.item_type,
                item_id=item.item_id,
                item_title=assessment_scoring.resolve_item_title(db, item),
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
        )

    total = assessment_scoring.compute_weighted_score(db, assessment, student_id)
    cohort = assessment_scoring.cohort_average(db, assessment)
    above = (total > cohort) if (total is not None and cohort is not None) else None

    return StudentReportAssessmentBlock(
        assessment_id=assessment.id,
        assessment_title=assessment.title,
        submitted_at=session.submitted_at,
        total_weighted_score=total,
        cohort_average=cohort,
        above_average=above,
        student_count=len(assessment_scoring.roster_user_ids(db, assessment.id)),
        items=component_scores,
    )


@router.get("/students/{student_id}", response_model=StudentFullReport)
def get_student_full_report(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Staff view of one student: practice completion plus a per-assessment score
    breakdown (submitted assessments only) with cohort comparison."""
    student = db.query(User).filter(User.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    # Latest submitted session per assessment, newest first. attempt_complete==1 is
    # the single-attempt "submitted" flag (see AssessmentSession).
    sessions = (
        db.query(AssessmentSession)
        .filter(
            AssessmentSession.user_id == student_id,
            AssessmentSession.attempt_complete == 1,
        )
        .order_by(AssessmentSession.submitted_at.desc())
        .all()
    )

    blocks: list[StudentReportAssessmentBlock] = []
    seen_assessments: set[int] = set()
    for session in sessions:
        if session.assessment_id in seen_assessments:
            continue
        assessment = (
            db.query(Assessment)
            .filter(Assessment.id == session.assessment_id, Assessment.is_deleted == 0)
            .first()
        )
        if not assessment:
            continue
        seen_assessments.add(session.assessment_id)
        blocks.append(_assessment_block(db, assessment, session, student_id))

    return StudentFullReport(
        student_id=student.id,
        student_email=student.email,
        student_name=student.name,
        class_group=student.class_group,
        summary=_build_summary(db, student_id),
        assessments=blocks,
    )
