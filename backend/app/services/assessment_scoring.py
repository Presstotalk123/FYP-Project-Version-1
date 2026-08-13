"""Weighted assessment scoring.

Combines a student's per-item activity into a single weighted score (0-100) using the
per-question `weight` set by staff. Each item type yields a correctness fraction (0.0-1.0):

- sql_question: 1.0 if the student has any correct attempt, else 0.0 (binary).
- sql_lab / graph_lab: distinct correct tasks / total tasks.
- er_question: the latest LLM-graded percent / 100 (from the ERD tutor conversation).

The weighted total is Σ(weight_i * fraction_i) normalised to 100 so it stays a percentage
even if the stored weights don't sum to exactly 100. Returns None when the assessment has
no weightage at all (legacy/unweighted), so callers can show "N/A" instead of a false 0.
"""
import json
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_item_visit import AssessmentItemVisit
from app.models.assessment_session import AssessmentSession
from app.models.attempt import Attempt
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.lab import Lab
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.question import Question
from app.services.erd_tutor import persistence as erd_persistence


def er_percent(db: Session, question_id: int, student_id: int) -> Optional[float]:
    """Latest LLM-graded percent (0-100) for a student's assessment ER question, or None.

    Assessment ER questions go through the standalone ERD-tutor path, which keeps a single
    conversation per (user, question) with the latest grade in `last_submit_score` JSON.
    """
    conv = erd_persistence.find_conversation(
        db,
        user_id=student_id,
        context_type="standalone",
        er_diagram_question_id=question_id,
    )
    if not conv or not conv.last_submit_score:
        return None
    try:
        data = json.loads(conv.last_submit_score)
    except (ValueError, TypeError):
        return None
    try:
        return float(data.get("percent"))
    except (TypeError, ValueError):
        return None


@dataclass
class ItemScoreDetail:
    """Per-student, per-item scoring detail: the correctness fraction plus the raw
    per-type fields needed to render an activity breakdown (attempt counts, lab task
    counts, ER visit status)."""
    fraction: float
    has_correct_attempt: Optional[bool] = None
    attempt_count: Optional[int] = None
    visited: Optional[bool] = None
    tasks_correct: Optional[int] = None
    tasks_total: Optional[int] = None
    # The specific task ids this student solved (lab items only) — lets callers tally
    # per-task success rates across a roster without an extra query.
    correct_task_ids: Optional[set] = None


def item_score_detail(
    db: Session,
    item: AssessmentItem,
    student_id: int,
    session_id: Optional[int] = None,
) -> ItemScoreDetail:
    """Correctness fraction (0.0-1.0) and raw activity detail for a single assessment item.

    `session_id` (the student's AssessmentSession.id) is only used for the er_question
    "visited" flag; pass None when that detail isn't needed.
    """
    if item.item_type == "sql_question":
        attempts = (
            db.query(Attempt)
            .filter(Attempt.user_id == student_id, Attempt.question_id == item.item_id)
            .all()
        )
        has_correct = any(bool(a.is_correct) for a in attempts)
        return ItemScoreDetail(
            fraction=1.0 if has_correct else 0.0,
            has_correct_attempt=has_correct,
            attempt_count=len(attempts),
        )

    if item.item_type in ("sql_lab", "graph_lab"):
        total_tasks = (
            db.query(LabTask)
            .filter(LabTask.lab_id == item.item_id, LabTask.is_deleted == 0)
            .count()
        )
        correct_task_ids = {
            row[0] for row in (
                db.query(LabTaskSubmission.task_id)
                .filter(
                    LabTaskSubmission.user_id == student_id,
                    LabTaskSubmission.lab_id == item.item_id,
                    LabTaskSubmission.is_correct == 1,
                )
                .distinct()
                .all()
            )
        }
        correct_tasks = len(correct_task_ids)
        fraction = min(1.0, correct_tasks / total_tasks) if total_tasks > 0 else 0.0
        return ItemScoreDetail(
            fraction=fraction,
            tasks_correct=correct_tasks,
            tasks_total=total_tasks,
            correct_task_ids=correct_task_ids,
        )

    if item.item_type == "er_question":
        visited = False
        if session_id is not None:
            visited = (
                db.query(AssessmentItemVisit)
                .filter(
                    AssessmentItemVisit.session_id == session_id,
                    AssessmentItemVisit.assessment_item_id == item.id,
                )
                .first()
            ) is not None
        pct = er_percent(db, item.item_id, student_id)
        return ItemScoreDetail(
            fraction=(pct / 100.0) if pct is not None else 0.0,
            visited=visited,
        )

    return ItemScoreDetail(fraction=0.0)


def item_score_fraction(db: Session, item: AssessmentItem, student_id: int) -> float:
    """Correctness fraction (0.0-1.0) for a single assessment item."""
    return item_score_detail(db, item, student_id).fraction


def compute_weighted_score(db: Session, assessment: Assessment, student_id: int) -> Optional[float]:
    """Weighted total (0-100) for a student, or None if the assessment carries no weightage."""
    items = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.assessment_id == assessment.id)
        .all()
    )
    total_weight = sum(i.weight for i in items)
    if total_weight <= 0:
        return None
    earned = sum(i.weight * item_score_fraction(db, i, student_id) for i in items)
    return round(earned / total_weight * 100, 1)


def roster_user_ids(db: Session, assessment_id: int) -> list[int]:
    """Distinct user ids of everyone who has a session on this assessment.

    The whole cohort for cohort-average purposes — mirrors the endpoint's
    `_student_roster` but returns ids only (one row per user is implicit in the
    distinct set, so the "latest session per user" collapse isn't needed here).
    """
    rows = (
        db.query(AssessmentSession.user_id)
        .filter(AssessmentSession.assessment_id == assessment_id)
        .distinct()
        .all()
    )
    return [uid for (uid,) in rows]


def cohort_average(db: Session, assessment: Assessment) -> Optional[float]:
    """Mean weighted score (0-100) across everyone who took the assessment.

    Algebraically identical to item-analytics' `avg_weighted_score`. Returns None
    when the assessment is unweighted or no student has a scorable weighted total.
    """
    scores = [
        s
        for uid in roster_user_ids(db, assessment.id)
        if (s := compute_weighted_score(db, assessment, uid)) is not None
    ]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def resolve_item_title(db: Session, item: AssessmentItem) -> str:
    """Display title for a polymorphic assessment item (SQL/ER question or lab)."""
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
