"""Relational-algebra questions (FYP). Mounted under /ra by endpoints/ra.py.

Staff
  POST   /ra/questions/validate        check a draft and preview its test databases (nothing saved)
  POST   /ra/questions/schema-from-text  turn STUDENT(*Sid, Sname) lines into CREATE TABLE statements
  POST   /ra/questions/example-data    example data for a question with no INSERTs (Regenerate)
  POST   /ra/questions                 create
  GET    /ra/questions/{id}/edit       everything, including the model answer
  PUT    /ra/questions/{id}            update (test databases rebuilt if the content changed)
  DELETE /ra/questions/{id}            soft delete
  POST   /ra/questions/{id}/publish    show it to students (the Problems list's publish button)
  POST   /ra/questions/{id}/unpublish  hide it from students
Everyone signed in (students see published bank questions only)
  GET    /ra/questions                 the list, with this user's attempts and whether solved
  GET    /ra/questions/{id}            the question as students see it (no model answer)
  POST   /ra/questions/{id}/check      run an answer to one part step by step; not graded, not recorded
  POST   /ra/questions/{id}/submit     grade an answer to one part and record the attempt
  GET    /ra/questions/{id}/attempts   this user's own attempts (every part)

A question has one or more parts sharing its schema and data; answers name their part
(``part_id``, optional when there is only one). A multi-step question's answers are its
boxes (``step_answers``); the type switch and its preview are in ra_formats.py.

Every route 404s while RA_ENABLED is off (the dependency on the parent router).
"""
import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.ra import Database, RAError, evaluate
from app.core.ra.grader import Checkpoint
from app.core.ra.text_schema import sql_from_text
from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.models.ra_question import RAQuestion
from app.models.ra_question_part import RAQuestionPart
from app.models.user import User
from app.schemas.ra import (CheckpointIn, EvalOut, GradeOut, RAAnswerIn, RAAttemptOut, RACheckOut,
                            RAErrorOut, RAExampleDataIn, RAExampleDataOut, RAQuestionIn, RAQuestionListItem, RAQuestionOut, RAQuestionStaffOut,
                            RAQuestionValidateIn, RAQuestionValidateOut, RASchemaTextIn, RASchemaTextOut,
                            RASubmitOut, RelationOut, ShownResultOut,
                            SuiteSummaryOut)
from app.core.ra.answer_format import MIXED, MULTI_STEP
from app.schemas.ra import RABoxCheckOut, StepMarkingOut
from app.services.ra import assessment as ra_assessment, formats, grading, multi_step, questions as svc

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
                         {"source": e.source, "part": e.part, "step": e.step, "error": e.error.to_dict(),
                          "message": e.error.message})


def _student_out(db: Session, q: RAQuestion, user: User) -> dict:
    hide = bool(q.hide_correctness)      # don't reveal correctness through progress badges
    progress = svc.part_progress(db, user)
    parts = []
    for part in svc.parts_of(db, q):
        attempts, solved = progress.get(part.id, (0, False))
        parts.append(dict(id=part.id, label=part.label, description=part.description, marks=part.marks,
                          attempts=attempts, solved=solved and not hide,
                          submissions_used=ra_assessment.submissions_used(db, part, user),
                          steps=multi_step.public_steps(part) if part.steps_json else None))
    shown, source = svc.shown_database(q)
    return dict(id=q.id, title=q.title, description=q.description, difficulty=q.difficulty,
                relations=(shown or Database.from_sql(q.schema_sql)).to_dict(), data_source=source,
                has_data=bool((q.data_sql or "").strip()), answer_format=q.answer_format or MIXED,
                show_step_direction=bool(q.show_step_direction), hide_correctness=hide,
                attempts=sum(p["attempts"] for p in parts),
                solved=bool(parts) and all(p["solved"] for p in parts),
                parts=parts, assessment_id=q.owner_assessment_id,
                max_submissions=ra_assessment.submission_limit(db, q))


def _parts_in(body: RAQuestionIn) -> List[dict]:
    return [dict(id=p.id, label=p.label, description=p.description, marks=p.marks, model_answer=p.model_answer,
                 checkpoints=[c.model_dump() for c in p.checkpoints] if p.checkpoints else None,
                 steps=[s.model_dump() for s in p.steps] if p.steps is not None else None)
            for p in body.parts]


def _eval_out(result: dict) -> EvalOut:
    return EvalOut(**result)


# ── staff ────────────────────────────────────────────────────────────────────
@router.post("/validate", response_model=RAQuestionValidateOut)
def validate_question(body: RAQuestionValidateIn, _staff: User = Depends(require_staff_role)):
    """Check one part's model answer (a multi-step part: its steps) on the question's schema and data."""
    spec = dict(model_answer=body.model_answer, marks=1,
                checkpoints=[c.model_dump() for c in body.checkpoints] if body.checkpoints else None,
                steps=[s.model_dump() for s in body.steps] if body.steps is not None else None)
    try:
        spec = formats.part_spec(body.answer_format, spec, 0, Database.from_sql(body.schema_sql), svc.eval_options())
    except RAError as e:
        return RAQuestionValidateOut(ok=False, error_source="schema", error=RAErrorOut.from_engine(e))
    except formats.FormatError as e:
        return RAQuestionValidateOut(ok=False, error_source="steps" if e.source == "steps" else "model_answer",
                                     error=RAErrorOut.from_engine(e.error), error_step=e.step)
    checkpoints = [Checkpoint(c["statement"], c["label"]) for c in spec["checkpoints"]] if spec.get("checkpoints") else None
    try:
        prepared = svc.prepare(body.schema_sql, body.data_sql, spec["model_answer"],
                               checkpoints=checkpoints, bag=body.compare_bags)
    except svc.QuestionInputError as e:
        return RAQuestionValidateOut(ok=False, error_source=e.source, error=RAErrorOut.from_engine(e.error))
    example = body.example_data_sql if not (body.data_sql or "").strip() else None
    if example and svc.fits_schema(body.schema_sql, example):
        db, source = Database.from_sql(body.schema_sql, example), "example"
    else:
        db, source = grading.structure_database(prepared)
    model = evaluate(prepared.model, db, options=svc.eval_options())
    relations = Database.from_sql(body.schema_sql, body.data_sql).to_dict()
    return RAQuestionValidateOut(
        ok=True, relations=[RelationOut(**r) for r in relations],
        suite=SuiteSummaryOut(**prepared.suite_summary()),
        model_result=EvalOut(columns=model.columns, rows=[list(r) for r in model.rows], row_count=len(model.rows),
                             steps=model.statements, warnings=[RAErrorOut.from_engine(w) for w in model.warnings]),
        model_result_source=source,
        checkpoints=[CheckpointIn(statement=c.statement, label=c.label) for c in prepared.checkpoints])


@router.post("/schema-from-text", response_model=RASchemaTextOut)
def schema_from_text(body: RASchemaTextIn, _staff: User = Depends(require_staff_role)):
    """CREATE TABLE statements for a schema written as text (staff edit them before saving)."""
    try:
        schema_sql = sql_from_text(body.text, link=body.link_keys)
        relations = Database.from_sql(schema_sql).to_dict()
    except RAError as e:
        return RASchemaTextOut(ok=False, error=RAErrorOut.from_engine(e))
    return RASchemaTextOut(ok=True, schema_sql=schema_sql, relations=[RelationOut(**r) for r in relations])


@router.post("/example-data", response_model=RAExampleDataOut)
def example_data(body: RAExampleDataIn, _staff: User = Depends(require_staff_role)):
    """Example data for the staff form when its INSERT box is empty (nothing saved): the
    form's ``current`` one if the schema still accepts it, else one built from the schema
    and model answers (those that can't be read yet are ignored); ``variant`` > 0 gives another."""
    try:
        if body.current and svc.fits_schema(body.schema_sql, body.current):
            data_sql = body.current
        else:
            data_sql = svc.example_sql(body.schema_sql, body.model_answers, body.variant)
        relations = Database.from_sql(body.schema_sql, data_sql).to_dict()
    except RAError as e:
        return RAExampleDataOut(ok=False, error=RAErrorOut.from_engine(e))
    return RAExampleDataOut(ok=True, data_sql=data_sql, relations=[RelationOut(**r) for r in relations])


def _apply(db: Session, q: RAQuestion, body: RAQuestionIn) -> None:
    q.title, q.description, q.difficulty = body.title, body.description, body.difficulty
    q.show_step_direction = int(body.show_step_direction)
    q.assessment_step_direction = int(body.assessment_step_direction)
    q.hide_correctness = int(body.hide_correctness)
    q.is_published = int(body.is_published)
    try:
        svc.save_content(db, q, schema_sql=body.schema_sql, data_sql=body.data_sql, parts=_parts_in(body),
                         compare_bags=body.compare_bags, example_data_sql=body.example_data_sql,
                         answer_format=body.answer_format)
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
                    suite=json.loads(row.suite_summary_json) if row.suite_summary_json else None,
                    steps=json.loads(row.steps_json) if row.steps_json else None)
    out.update(schema_sql=q.schema_sql, data_sql=q.data_sql or "", example_data_sql=svc.example_sql_for(q),
               compare_bags=bool(q.compare_bags),
               is_published=bool(q.is_published), assessment_step_direction=bool(q.assessment_step_direction),
               has_attempts=formats.locked(db, q))
    return out


def _set_published(db: Session, question_id: int, staff: User, published: bool) -> dict:
    q = _get(db, question_id, staff)
    q.is_published = int(published)
    db.commit()
    return {"id": q.id, "is_published": published}


@router.post("/{question_id}/publish")
def publish_question(question_id: int, db: Session = Depends(get_db), staff: User = Depends(require_staff_role)):
    return _set_published(db, question_id, staff, True)


@router.post("/{question_id}/unpublish")
def unpublish_question(question_id: int, db: Session = Depends(get_db), staff: User = Depends(require_staff_role)):
    return _set_published(db, question_id, staff, False)


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
                                      parts_total=p.parts_total, parts_solved=0 if hide else p.parts_solved,
                                      created_by=q.created_by, created_at=q.created_at))
    return out


@router.get("/{question_id}", response_model=RAQuestionOut)
def get_question(question_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _student_out(db, _get(db, question_id, user), user)


@router.post("/{question_id}/check", response_model=RACheckOut)
def check_answer(question_id: int, body: RAAnswerIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    q = _get(db, question_id, user)
    part = _part(db, q, body.part_id)
    if (q.answer_format or MIXED) == MULTI_STEP and part.steps_json:
        out = multi_step.check(q, part, body.step_answers or [])
        return RACheckOut(ok=True, source=out["source"], boxes=[RABoxCheckOut(**b) for b in out["boxes"]])
    if not (body.answer or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Write an answer first.")
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
    if (q.answer_format or MIXED) == MULTI_STEP and part.steps_json:
        return _submit_steps(db, user, q, part, body.step_answers or [])
    if not (body.answer or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Write an answer first.")
    try:
        submission = svc.submit(db, user, q, part, body.answer)
    except svc.WrongFormat as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    limit, used = svc.submission_counts(db, user, q, part)
    out = RASubmitOut(attempt_id=submission.attempt.id, part_id=part.id, max_submissions=limit, submissions_used=used)
    shown = svc.for_student(q, submission.result) if not svc.is_staff(user) else submission.result.to_dict()
    if shown is not None:
        out.grade = GradeOut(**shown)
        if submission.result.verdict != "invalid_expression":
            comparison = svc.shown_comparison(q, part, body.answer)
            if comparison is not None:
                out.shown = ShownResultOut(**comparison)
    if submission.result.verdict != "invalid_expression":
        try:
            result, source, _relations = svc.check(q, part, body.answer)
            out.structure, out.structure_source = _eval_out(result), source
        except RAError:
            pass
    return out


def _submit_steps(db: Session, user: User, q: RAQuestion, part: RAQuestionPart, answers: List[str]) -> RASubmitOut:
    """Submit a multi-step answer: marked per step (services/ra/multi_step.py)."""
    attempt, marking = multi_step.submit(db, user, q, part, answers)
    limit, used = svc.submission_counts(db, user, q, part)
    out = RASubmitOut(attempt_id=attempt.id, part_id=part.id, max_submissions=limit, submissions_used=used)
    staff = svc.is_staff(user)
    shown = svc.for_student(q, marking.grade) if not staff else marking.grade.to_dict()
    if shown is not None:
        out.grade = GradeOut(**shown)
        rows, source = multi_step.results_for(q, part, json.loads(attempt.step_answers_json), marking, staff)
        out.marking = StepMarkingOut(earned=marking.earned, total=marking.total, final_correct=marking.grade.correct,
                                     source=source, steps=rows)
    return out


@router.get("/{question_id}/attempts", response_model=List[RAAttemptOut])
def my_attempts(question_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = _get(db, question_id, user)
    hide = bool(q.hide_correctness) and not svc.is_staff(user)
    return [RAAttemptOut(id=a.id, part_id=a.part_id, answer=a.answer, created_at=a.created_at,
                         verdict=None if hide else a.verdict, is_correct=None if hide else bool(a.is_correct),
                         step_answers=json.loads(a.step_answers_json) if a.step_answers_json else None,
                         marks_earned=None if hide else a.marks_earned)
            for a in svc.history(db, user, q)]
