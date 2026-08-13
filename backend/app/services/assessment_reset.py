"""
Reset one student's attempt on one assessment — a staff clean-slate action.

Assessment content is cloned per assessment (see assessment_clone.py): when published,
each AssessmentItem.item_id points to a clone whose id appears ONLY inside this assessment.
So a student's attempt rows for the assessment are exactly the rows keyed to
(user_id, item.item_id) — deleting them cannot touch the student's standalone practice or
any other assessment.

SAFETY: the caller must ensure the assessment is published (item_id == clone id). This
service additionally verifies each content row's owner_assessment_id == assessment.id before
deleting, so it can never purge a master/practice row even if called out of contract.

Does not commit; the caller owns the transaction.
"""
from sqlalchemy.orm import Session

from app.core.cache import Ns, bump_version
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.models.assessment_item_visit import AssessmentItemVisit
from app.models.question import Question
from app.models.lab import Lab
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.attempt import Attempt
from app.models.progress import UserProgress
from app.models.lab_session import LabSession
from app.models.lab_attempt import LabAttempt
from app.models.lab_task_submission import LabTaskSubmission
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.erd_tutor_message import ErdTutorMessage
from app.utils.lab_db_manager import get_student_session_path
from app.utils.lab_cleanup import delete_session_file_with_retry


def _owns(db: Session, model, content_id: int, assessment_id: int) -> bool:
    """True only if the content row is a clone owned by this assessment (safety belt)."""
    row = db.query(model).filter(model.id == content_id).first()
    return row is not None and row.owner_assessment_id == assessment_id


def _reset_sql_question(db: Session, student_id: int, content_id: int) -> int:
    deleted = (
        db.query(Attempt)
        .filter(Attempt.user_id == student_id, Attempt.question_id == content_id)
        .delete(synchronize_session=False)
    )
    db.query(UserProgress).filter(
        UserProgress.user_id == student_id,
        UserProgress.question_id == content_id,
    ).delete(synchronize_session=False)
    return deleted


def _reset_lab(db: Session, student_id: int, content_id: int) -> int:
    # Children first (they reference lab_sessions / lab_tasks), then sessions.
    db.query(LabTaskSubmission).filter(
        LabTaskSubmission.user_id == student_id,
        LabTaskSubmission.lab_id == content_id,
    ).delete(synchronize_session=False)
    db.query(LabAttempt).filter(
        LabAttempt.user_id == student_id,
        LabAttempt.lab_id == content_id,
    ).delete(synchronize_session=False)

    sessions = db.query(LabSession).filter(
        LabSession.user_id == student_id,
        LabSession.lab_id == content_id,
    ).all()
    n = len(sessions)
    # Delete the on-disk student DB file(s). Path is deterministic per (lab_id, user_id).
    delete_session_file_with_retry(get_student_session_path(content_id, student_id))
    for s in sessions:
        db.delete(s)
    return n


def _reset_er_question(db: Session, student_id: int, content_id: int) -> int:
    """Best-effort: only the langgraph ER-tutor engine persists anything here."""
    conv_ids = [
        c.id
        for c in db.query(ErdTutorConversation.id).filter(
            ErdTutorConversation.user_id == student_id,
            ErdTutorConversation.er_diagram_question_id == content_id,
        )
    ]
    if conv_ids:
        db.query(ErdTutorMessage).filter(
            ErdTutorMessage.conversation_id.in_(conv_ids)
        ).delete(synchronize_session=False)
        db.query(ErdTutorConversation).filter(
            ErdTutorConversation.id.in_(conv_ids)
        ).delete(synchronize_session=False)
    return len(conv_ids)


def reset_student_attempt(db: Session, assessment: Assessment, student_id: int) -> dict:
    """Erase a student's attempt data for the assessment's cloned items and remove their
    session(s) + visits (clearing the single-attempt completion lock). Returns a summary."""
    summary = {"sql_questions": 0, "labs": 0, "er_questions": 0, "sessions": 0}

    items = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.assessment_id == assessment.id)
        .all()
    )

    for item in items:
        content_id = item.item_id
        if item.item_type == "sql_question":
            if _owns(db, Question, content_id, assessment.id):
                summary["sql_questions"] += _reset_sql_question(db, student_id, content_id)
        elif item.item_type in ("sql_lab", "graph_lab"):
            if _owns(db, Lab, content_id, assessment.id):
                summary["labs"] += _reset_lab(db, student_id, content_id)
        elif item.item_type == "er_question":
            if _owns(db, ERDiagramQuestion, content_id, assessment.id):
                summary["er_questions"] += _reset_er_question(db, student_id, content_id)

    # Remove the assessment session(s) + their visits — a true clean slate. Deleting the
    # session clears attempt_complete, so the student can re-join while the assessment runs.
    session_ids = [
        s.id
        for s in db.query(AssessmentSession.id).filter(
            AssessmentSession.assessment_id == assessment.id,
            AssessmentSession.user_id == student_id,
        )
    ]
    if session_ids:
        db.query(AssessmentItemVisit).filter(
            AssessmentItemVisit.session_id.in_(session_ids)
        ).delete(synchronize_session=False)
        db.query(AssessmentSession).filter(
            AssessmentSession.id.in_(session_ids)
        ).delete(synchronize_session=False)
        summary["sessions"] = len(session_ids)

    # All the deletes above are bulk delete()s that bypass the ORM unit of work, so the
    # after_flush auto-invalidation won't fire — bump the analytics namespace explicitly
    # (the caller commits this in the same transaction).
    bump_version(db, Ns.ASSESSMENT_ANALYTICS)

    return summary
