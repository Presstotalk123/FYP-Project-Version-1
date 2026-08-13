"""Practice-completion counts for a single student.

Shared by the student-facing GET /student-report/summary and the staff-facing
GET /student-report/students/{id}. All functions take a plain user_id so they work
for "me" and for "any student" alike. Kept out of the endpoint module so both
callers use exactly the same completion semantics.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.models.progress import UserProgress
from app.models.question import Question
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.lab import Lab
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission

logger = logging.getLogger(__name__)


def sql_questions_completed(db: Session, user_id: int) -> int:
    """Standalone (bank) SQL questions the student has completed.

    Mirrors GET /attempts/progress: a question counts when its UserProgress row is
    flagged completed. Assessment-owned clones are excluded so the count reflects
    only the master practice bank.
    """
    return (
        db.query(UserProgress.id)
        .join(Question, UserProgress.question_id == Question.id)
        .filter(
            UserProgress.user_id == user_id,
            UserProgress.completed == 1,
            Question.is_deleted == 0,
            Question.owner_assessment_id.is_(None),
        )
        .count()
    )


def erd_questions_completed(db: Session, user_id: int) -> int:
    """Standalone (bank) ER questions the student has passed.

    Replicates GET /er-diagram/progress: completion reads the grader's own "pass"
    verdict out of the conversation's last_submit_score JSON rather than
    thresholding a percent. An unreadable row degrades to not-completed.
    """
    rows = (
        db.query(ErdTutorConversation.last_submit_score)
        .join(
            ERDiagramQuestion,
            ERDiagramQuestion.id == ErdTutorConversation.er_diagram_question_id,
        )
        .filter(
            ErdTutorConversation.user_id == user_id,
            ErdTutorConversation.context_type == "standalone",
            ErdTutorConversation.er_diagram_question_id.isnot(None),
            ErdTutorConversation.last_submit_score.isnot(None),
            ERDiagramQuestion.is_deleted == 0,
            ERDiagramQuestion.owner_assessment_id.is_(None),
        )
        .all()
    )

    completed = 0
    for (raw_score,) in rows:
        try:
            data = json.loads(raw_score)
            if isinstance(data, dict) and data.get("label") == "pass":
                completed += 1
        except (TypeError, ValueError):
            logger.warning("Unreadable last_submit_score for user %s", user_id)
    return completed


def labs_completed_by_type(db: Session, user_id: int) -> tuple[int, int]:
    """(sql_labs_completed, graph_labs_completed).

    A lab is complete when the student has a correct submission for every one of its
    non-deleted tasks (the same fraction==1.0 rule as assessment_scoring's lab
    branch). Only published master-bank labs are considered.
    """
    labs = (
        db.query(Lab.id, Lab.lab_type)
        .filter(
            Lab.is_published == 1,
            Lab.is_deleted == 0,
            Lab.owner_assessment_id.is_(None),
        )
        .all()
    )

    sql_done = 0
    graph_done = 0
    for lab_id, lab_type in labs:
        total_tasks = (
            db.query(LabTask.id)
            .filter(LabTask.lab_id == lab_id, LabTask.is_deleted == 0)
            .count()
        )
        if total_tasks == 0:
            continue

        correct_tasks = (
            db.query(LabTaskSubmission.task_id)
            .filter(
                LabTaskSubmission.user_id == user_id,
                LabTaskSubmission.lab_id == lab_id,
                LabTaskSubmission.is_correct == 1,
            )
            .distinct()
            .count()
        )

        if correct_tasks >= total_tasks:
            if lab_type == "graph":
                graph_done += 1
            else:
                sql_done += 1

    return sql_done, graph_done
