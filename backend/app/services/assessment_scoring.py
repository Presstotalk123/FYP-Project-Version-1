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
from typing import Optional

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.attempt import Attempt
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
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


def item_score_fraction(db: Session, item: AssessmentItem, student_id: int) -> float:
    """Correctness fraction (0.0-1.0) for a single assessment item."""
    if item.item_type == "sql_question":
        has_correct = (
            db.query(Attempt.id)
            .filter(
                Attempt.user_id == student_id,
                Attempt.question_id == item.item_id,
                Attempt.is_correct == 1,
            )
            .first()
        ) is not None
        return 1.0 if has_correct else 0.0

    if item.item_type in ("sql_lab", "graph_lab"):
        total_tasks = (
            db.query(LabTask)
            .filter(LabTask.lab_id == item.item_id, LabTask.is_deleted == 0)
            .count()
        )
        if total_tasks == 0:
            return 0.0
        correct_tasks = (
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
        return min(1.0, correct_tasks / total_tasks)

    if item.item_type == "er_question":
        pct = er_percent(db, item.item_id, student_id)
        return (pct / 100.0) if pct is not None else 0.0

    return 0.0


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
