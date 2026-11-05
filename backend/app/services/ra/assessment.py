"""Relational-algebra questions inside assessments (item_type "ra_question").

The shared assessment code (assessment_clone, assessment_scoring, assessment_reset, the
assessments endpoints) calls into this module from one short branch each, so all RA
behaviour lives here. It follows the SQL-question rules exactly:

  * Publishing an assessment clones each RA question (owner_assessment_id set) with its
    stored test databases, so editing the bank question afterwards never changes a live
    exam, and every student in it is graded on the same databases.
  * A clone is reachable only by a student with an active session in a live assessment
    that contains it, and staff.
  * The assessment timer is enforced on Submit, and AssessmentItem.max_queries caps the
    number of Submits for each part (Check never counts: it is not graded).
  * Scoring: each part earns its marks once any submission to it is correct (or a staff
    override says so); the item's fraction is the marks earned over the question's total.
    A one-part question is therefore binary, exactly like sql_question. A multi-step
    part may also earn some of its marks (its steps', core/ra/step_marking.py): the
    part then earns the best of its submissions.
"""
from typing import Dict, Iterable, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.models.ra_attempt import RAAttempt
from app.models.ra_question import RAQuestion
from app.models.ra_question_part import RAQuestionPart
from app.models.user import User

ITEM_TYPE = "ra_question"

# An attempt counts as correct when staff overrode it to correct, or the grader said so
# and nobody overrode it.
_EFFECTIVE_CORRECT = func.coalesce(RAAttempt.override_is_correct, RAAttempt.is_correct)


def effective_marks(override_is_correct, is_correct, marks_earned, part_marks: int) -> int:
    """The marks one attempt earns: all or nothing by a staff override if there is one,
    else the step marks it earned (multi-step), else all of them when it is correct."""
    part_marks = part_marks or 0
    if override_is_correct is not None:
        return part_marks if override_is_correct else 0
    if marks_earned is not None:
        return max(0, min(int(marks_earned), part_marks))
    return part_marks if is_correct else 0


# ── publishing ───────────────────────────────────────────────────────────────
def clone_for_assessment(db: Session, question_id: int, assessment_id: int, hide_correctness: int = 0) -> int:
    """Copy a bank RA question into an assessment-owned clone; returns the clone's id."""
    from app.services.assessment_clone import AssessmentCloneError

    master = db.query(RAQuestion).filter(RAQuestion.id == question_id, RAQuestion.is_deleted == 0).first()
    if master is None:
        raise AssessmentCloneError(f"RA question {question_id} not found for cloning")
    clone = RAQuestion(
        title=master.title, description=master.description, difficulty=master.difficulty,
        schema_sql=master.schema_sql, data_sql=master.data_sql, model_answer=master.model_answer,
        example_data_sql=master.example_data_sql,
        checkpoints_json=master.checkpoints_json,
        # In an exam the question's own "in assessments" choice decides, never practice's.
        show_step_direction=master.assessment_step_direction if not hide_correctness else 0,
        assessment_step_direction=master.assessment_step_direction,
        compare_bags=master.compare_bags, hide_correctness=hide_correctness, answer_format=master.answer_format,
        is_published=0, is_deleted=0,
        suite_json=master.suite_json, suite_summary_json=master.suite_summary_json,
        created_by=master.created_by, owner_assessment_id=assessment_id,
    )
    db.add(clone)
    db.flush()
    for part in (db.query(RAQuestionPart)
                 .filter(RAQuestionPart.question_id == master.id, RAQuestionPart.is_deleted == 0)
                 .order_by(RAQuestionPart.position, RAQuestionPart.id)):
        db.add(RAQuestionPart(
            question_id=clone.id, position=part.position, label=part.label, description=part.description,
            marks=part.marks, model_answer=part.model_answer, checkpoints_json=part.checkpoints_json,
            steps_json=part.steps_json,
            suite_json=part.suite_json, suite_summary_json=part.suite_summary_json, is_deleted=0))
    db.flush()
    return clone.id


def delete_clones(db: Session, assessment_id: int) -> None:
    """Soft-delete an assessment's RA clones (attempts stay, for history)."""
    db.query(RAQuestion).filter(RAQuestion.owner_assessment_id == assessment_id, RAQuestion.is_deleted == 0) \
        .update({RAQuestion.is_deleted: 1}, synchronize_session=False)


def owns(db: Session, question_id: int, assessment_id: int) -> bool:
    return db.query(RAQuestion.id).filter(RAQuestion.id == question_id,
                                          RAQuestion.owner_assessment_id == assessment_id).first() is not None


def reset_student(db: Session, student_id: int, question_id: int) -> int:
    """Delete a student's attempts on one (cloned) RA question; returns how many."""
    return db.query(RAAttempt).filter(RAAttempt.user_id == student_id, RAAttempt.question_id == question_id) \
        .delete(synchronize_session=False)


# ── scoring ──────────────────────────────────────────────────────────────────
def scores(db: Session, user_ids: Iterable[int], question_ids: Iterable[int]
           ) -> Tuple[Dict[Tuple[int, int], float], Dict[Tuple[int, int], int]]:
    """{(user, question): fraction of the question's marks earned}, and
    {(user, question): attempts}. Pairs without attempts are left out (fraction 0)."""
    user_ids, question_ids = list(user_ids), list(question_ids)
    if not user_ids or not question_ids:
        return {}, {}
    marks: Dict[int, int] = {}
    total: Dict[int, int] = {}
    for pid, qid, m in (db.query(RAQuestionPart.id, RAQuestionPart.question_id, RAQuestionPart.marks)
                        .filter(RAQuestionPart.question_id.in_(question_ids), RAQuestionPart.is_deleted == 0)):
        marks[pid] = m or 0
        total[qid] = total.get(qid, 0) + (m or 0)
    attempts: Dict[Tuple[int, int], int] = {}
    best: Dict[Tuple[int, int, int], int] = {}
    rows = (db.query(RAAttempt.user_id, RAAttempt.question_id, RAAttempt.part_id, RAAttempt.override_is_correct,
                     RAAttempt.is_correct, RAAttempt.marks_earned)
            .filter(RAAttempt.user_id.in_(user_ids), RAAttempt.question_id.in_(question_ids)).all())
    for uid, qid, pid, override, correct, marks_earned in rows:
        attempts[(uid, qid)] = attempts.get((uid, qid), 0) + 1
        if pid in marks:
            got = effective_marks(override, correct, marks_earned, marks[pid])
            best[(uid, qid, pid)] = max(best.get((uid, qid, pid), 0), got)
    earned: Dict[Tuple[int, int], int] = {}
    for (uid, qid, _pid), got in best.items():
        if got:
            earned[(uid, qid)] = earned.get((uid, qid), 0) + got
    fractions = {key: (got / total[key[1]] if total.get(key[1]) else 0.0) for key, got in earned.items()}
    return fractions, attempts


def score_detail(db: Session, question_id: int, student_id: int) -> Tuple[float, int]:
    """(fraction of the marks earned, number of attempts) for one student and question."""
    fractions, attempts = scores(db, [student_id], [question_id])
    key = (student_id, question_id)
    return fractions.get(key, 0.0), attempts.get(key, 0)


def titles(db: Session, question_ids: Iterable[int]) -> Dict[int, str]:
    ids = list(question_ids)
    if not ids:
        return {}
    return dict(db.query(RAQuestion.id, RAQuestion.title).filter(RAQuestion.id.in_(ids)).all())


def title(db: Session, question_id: int) -> str:
    return titles(db, [question_id]).get(question_id) or f"RA Question #{question_id}"


# ── taking an assessment ─────────────────────────────────────────────────────
def accessible_via_assessment(db: Session, q: RAQuestion, user: User) -> bool:
    """Does the student have an active session in a live assessment containing this clone?
    Mirrors questions._question_accessible_via_assessment."""
    if q.owner_assessment_id is None:
        return False
    return (db.query(AssessmentSession.id)
            .join(Assessment, Assessment.id == AssessmentSession.assessment_id)
            .join(AssessmentItem, AssessmentItem.assessment_id == Assessment.id)
            .filter(AssessmentSession.user_id == user.id, AssessmentSession.is_active == 1,
                    (Assessment.is_running == 1) | (Assessment.gateway_enabled == 1),
                    AssessmentItem.item_type == ITEM_TYPE, AssessmentItem.item_id == q.id)
            .first()) is not None


def submission_limit(db: Session, q: RAQuestion) -> Optional[int]:
    """The assessment item's max_queries, used as the maximum number of Submits."""
    if q.owner_assessment_id is None:
        return None
    row = (db.query(AssessmentItem.max_queries)
           .filter(AssessmentItem.assessment_id == q.owner_assessment_id,
                   AssessmentItem.item_type == ITEM_TYPE, AssessmentItem.item_id == q.id).first())
    return row[0] if row else None


def submissions_used(db: Session, part: RAQuestionPart, user: User) -> int:
    return db.query(RAAttempt).filter(RAAttempt.user_id == user.id, RAAttempt.part_id == part.id).count()


def guard_submit(db: Session, q: RAQuestion, part: RAQuestionPart, user: User, is_staff: bool) -> None:
    """Before grading an assessment clone: the attempt must still be running and within
    its time, and a student must have Submits left for this part. Staff (preview) are
    never limited."""
    from app.services.assessment_timer import enforce_not_expired, get_active_assessment_session

    if q.owner_assessment_id is None or is_staff:
        return
    session = get_active_assessment_session(db, q.owner_assessment_id, user.id)
    if session is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Assessment has ended.")
    enforce_not_expired(db, session)               # 403 and finalize if past the deadline
    limit = submission_limit(db, q)
    if limit is not None and submissions_used(db, part, user) >= limit:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "You have reached the maximum number of submissions for this part.")
