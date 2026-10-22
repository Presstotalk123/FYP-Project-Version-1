"""Relational-algebra questions (FYP). Mounted under /ra by endpoints/ra.py.

Staff
  POST   /ra/questions/validate        check a draft and preview its test databases (nothing saved)
  POST   /ra/questions                 create
  GET    /ra/questions/{id}/edit       everything, including the model answer
  PUT    /ra/questions/{id}            update (test databases rebuilt if the content changed)
  DELETE /ra/questions/{id}            soft delete
Everyone signed in (students see published bank questions only)
  GET    /ra/questions                 the list, with this user's attempts and whether solved
  GET    /ra/questions/{id}            the question as students see it (no model answer)
  POST   /ra/questions/{id}/check      run an answer to one part step by step; not graded, not recorded
  POST   /ra/questions/{id}/submit     grade an answer to one part and record the attempt
  GET    /ra/questions/{id}/attempts   this user's own attempts (every part)

A question has one or more parts sharing its schema and data; answers name their part
(``part_id``, optional when there is only one).

Every route 404s while RA_ENABLED is off (the dependency on the parent router).
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.ra import Database, RAError, evaluate
from app.core.ra.grader import Checkpoint
from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.models.ra_question import RAQuestion
from app.models.ra_question_part import RAQuestionPart
from app.models.user import User
from app.schemas.ra import (CheckpointIn, EvalOut, GradeOut, RAAnswerIn, RAAttemptOut, RACheckOut,
                            RAErrorOut, RAQuestionIn, RAQuestionListItem, RAQuestionOut, RAQuestionStaffOut,
                            RAQuestionValidateIn, RAQuestionValidateOut, RASubmitOut, RelationOut,
                            SuiteSummaryOut)
from app.services.ra import assessment as ra_assessment, grading, questions as svc

router = APIRouter(prefix="/questions")


def _get(db: Session, question_id: int, user: User) -> RAQuestion:
    q = db.query(RAQuestion).filter(RAQuestion.id == question_id).first()
    if q is None or not svc.visible_to(db, q, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    return q


def _part(db: Session, q: RAQuestion, part_id) -> RAQuestionPart:
    try:
        return svc.part_for(db, q, part_id)
    except svc.PartNotFound as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


def _input_error(e: svc.QuestionInputError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                         {"source": e.source, "part": e.part, "error": e.error.to_dict(), "message": e.error.message})


def _student_out(db: Session, q: RAQuestion, user: User) -> dict:
    hide = bool(q.hide_correctness)      # don't reveal correctness through progress badges
    progress = svc.part_progress(db, user)
    parts = []
    for part in svc.parts_of(db, q):
        attempts, solved = progress.get(part.id, (0, False))
        parts.append(dict(id=part.id, label=part.label, description=part.description, marks=part.marks,
                          attempts=attempts, solved=solved and not hide,
                          submissions_used=ra_assessment.submissions_used(db, part, user)))
    return dict(id=q.id, title=q.title, description=q.description, difficulty=q.difficulty,
                relations=svc.relations_for(q), has_data=bool((q.data_sql or "").strip()),
                show_step_direction=bool(q.show_step_direction), hide_correctness=hide,
                attempts=sum(p["attempts"] for p in parts),
                solved=bool(parts) and all(p["solved"] for p in parts),
                parts=parts, assessment_id=q.owner_assessment_id,
                max_submissions=ra_assessment.submission_limit(db, q))


def _parts_in(body: RAQuestionIn) -> List[dict]:
    return [dict(id=p.id, label=p.label, description=p.description, marks=p.marks, model_answer=p.model_answer,
                 checkpoints=[c.model_dump() for c in p.checkpoints] if p.checkpoints else None)
            for p in body.parts]


def _eval_out(result: dict) -> EvalOut:
    return EvalOut(**result)


# ── staff ────────────────────────────────────────────────────────────────────
@router.post("/validate", response_model=RAQuestionValidateOut)
def validate_question(body: RAQuestionValidateIn, _staff: User = Depends(require_staff_role)):
    """Check one part's model answer on the question's schema and data."""
    checkpoints = [Checkpoint(c.statement, c.label) for c in body.checkpoints] if body.checkpoints else None
    try:
        prepared = svc.prepare(body.schema_sql, body.data_sql, body.model_answer,
                               checkpoints=checkpoints, bag=body.compare_bags)
    except svc.QuestionInputError as e:
        return RAQuestionValidateOut(ok=False, error_source=e.source, error=RAErrorOut.from_engine(e.error))
    db, source = grading.structure_database(prepared)
    model = evaluate(prepared.model, db, options=svc.eval_options())
    relations = Database.from_sql(body.schema_sql, body.data_sql).to_dict()
    return RAQuestionValidateOut(
        ok=True, relations=[RelationOut(**r) for r in relations],
        suite=SuiteSummaryOut(**prepared.suite.summary()),
        model_result=EvalOut(columns=model.columns, rows=[list(r) for r in model.rows], row_count=len(model.rows),
                             steps=model.statements, warnings=[RAErrorOut.from_engine(w) for w in model.warnings]),
        model_result_source=source,
        checkpoints=[CheckpointIn(statement=c.statement, label=c.label) for c in prepared.checkpoints])


def _apply(db: Session, q: RAQuestion, body: RAQuestionIn) -> None:
    q.title, q.description, q.difficulty = body.title, body.description, body.difficulty
    q.show_step_direction = int(body.show_step_direction)
    q.assessment_step_direction = int(body.assessment_step_direction)
    q.hide_correctness = int(body.hide_correctness)
    q.is_published = int(body.is_published)
    try:
        svc.save_content(db, q, schema_sql=body.schema_sql, data_sql=body.data_sql, parts=_parts_in(body),
                         compare_bags=body.compare_bags)
    except svc.QuestionInputError as e:
        db.rollback()
        raise _input_error(e)
    db.commit()
    db.refresh(q)


@router.post("", response_model=RAQuestionStaffOut, status_code=status.HTTP_201_CREATED)
def create_question(body: RAQuestionIn, db: Session = Depends(get_db), staff: User = Depends(require_staff_role)):
    q = RAQuestion(title=body.title, description=body.description, schema_sql="", data_sql="", model_answer="",
                   created_by=staff.id)
    db.add(q)
    db.flush()                            # parts need the question's id
    _apply(db, q, body)
    return _staff_out(db, q, staff)


@router.get("/{question_id}/edit", response_model=RAQuestionStaffOut)
def get_question_for_staff(question_id: int, db: Session = Depends(get_db),
                           staff: User = Depends(require_staff_role)):
    return _staff_out(db, _get(db, question_id, staff), staff)


@router.put("/{question_id}", response_model=RAQuestionStaffOut)
def update_question(question_id: int, body: RAQuestionIn, db: Session = Depends(get_db),
                    staff: User = Depends(require_staff_role)):
    q = _get(db, question_id, staff)
    _apply(db, q, body)
    return _staff_out(db, q, staff)


@router.delete("/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(question_id: int, db: Session = Depends(get_db), staff: User = Depends(require_staff_role)):
    q = _get(db, question_id, staff)
    q.is_deleted = 1
    db.commit()


def _staff_out(db: Session, q: RAQuestion, staff: User) -> dict:
    out = _student_out(db, q, staff)
    rows = {p.id: p for p in svc.parts_of(db, q)}
    for part in out["parts"]:
        row = rows[part["id"]]
        part.update(model_answer=row.model_answer,
                    checkpoints=json.loads(row.checkpoints_json) if row.checkpoints_json else None,
                    suite=json.loads(row.suite_summary_json) if row.suite_summary_json else None)
    out.update(schema_sql=q.schema_sql, data_sql=q.data_sql or "", compare_bags=bool(q.compare_bags),
               is_published=bool(q.is_published), assessment_step_direction=bool(q.assessment_step_direction))
    return out


# ── everyone ─────────────────────────────────────────────────────────────────
@router.get("", response_model=List[RAQuestionListItem])
def list_questions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    questions = svc.bank_questions(db, user)
    progress = svc.progress_by_question(db, user, [q.id for q in questions])
    out = []
    for q in questions:
        p = progress[q.id]
        hide = bool(q.hide_correctness)
        out.append(RAQuestionListItem(id=q.id, title=q.title, difficulty=q.difficulty,
                                      is_published=bool(q.is_published), has_data=bool((q.data_sql or "").strip()),
                                      attempts=p.attempts, solved=p.solved and not hide,
                                      parts_total=p.parts_total, parts_solved=0 if hide else p.parts_solved))
    return out


@router.get("/{question_id}", response_model=RAQuestionOut)
def get_question(question_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _student_out(db, _get(db, question_id, user), user)


@router.post("/{question_id}/check", response_model=RACheckOut)
def check_answer(question_id: int, body: RAAnswerIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    q = _get(db, question_id, user)
    part = _part(db, q, body.part_id)
    try:
        result, source, relations = svc.check(q, part, body.answer)
    except RAError as e:
        return RACheckOut(ok=False, error=RAErrorOut.from_engine(e))
    return RACheckOut(ok=True, result=_eval_out(result), source=source,
                      relations=[RelationOut(**r) for r in relations])


@router.post("/{question_id}/submit", response_model=RASubmitOut)
def submit_answer(question_id: int, body: RAAnswerIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    q = _get(db, question_id, user)
    part = _part(db, q, body.part_id)
    submission = svc.submit(db, user, q, part, body.answer)
    limit, used = svc.submission_counts(db, user, q, part)
    out = RASubmitOut(attempt_id=submission.attempt.id, part_id=part.id, max_submissions=limit, submissions_used=used)
    shown = svc.for_student(q, submission.result) if not svc.is_staff(user) else submission.result.to_dict()
    if shown is not None:
        out.grade = GradeOut(**shown)
    if submission.result.verdict != "invalid_expression":
        try:
            result, source, _relations = svc.check(q, part, body.answer)
            out.structure, out.structure_source = _eval_out(result), source
        except RAError:
            pass
    return out


@router.get("/{question_id}/attempts", response_model=List[RAAttemptOut])
def my_attempts(question_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = _get(db, question_id, user)
    hide = bool(q.hide_correctness) and not svc.is_staff(user)
    return [RAAttemptOut(id=a.id, part_id=a.part_id, answer=a.answer, created_at=a.created_at,
                         verdict=None if hide else a.verdict, is_correct=None if hide else bool(a.is_correct))
            for a in svc.history(db, user, q)]
