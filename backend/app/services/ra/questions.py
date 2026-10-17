"""Relational-algebra questions: saving, what each role may see, grading and attempts.

Saving a question validates it fully before anything is stored: the schema and data must
load, the model answer must run, and every checkpoint must name a step of the model
answer. Its test databases are then built once (core/ra/suite.py) and stored with it, so
every student is graded on exactly the same databases, and editing the schema, data or
model answer rebuilds them.

Students never receive the model answer, its steps or the test databases. Two per-
question switches limit feedback further: ``show_step_direction`` (the ✓/◐/○ comparison
of each step with the model's) and ``hide_correctness`` (only "submitted").
"""
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.ra import Database, EvalOptions, RAError, evaluate, parse
from app.core.ra.grader import Checkpoint, GradeResult, PreparedQuestion
from app.models.ra_attempt import RAAttempt
from app.models.ra_question import RAQuestion
from app.models.user import User, UserRole
from app.services.ra import grading


class QuestionInputError(Exception):
    """A staff input that cannot be saved; ``source`` says which field."""

    def __init__(self, source: str, error: RAError):
        super().__init__(error.message)
        self.source = source
        self.error = error


def eval_options() -> EvalOptions:
    return EvalOptions(aggregate_nulls=settings.RA_AGGREGATE_NULLS)


def is_staff(user: User) -> bool:
    return user.role in (UserRole.STAFF, UserRole.ADMIN)


def checkpoints_of(q: RAQuestion) -> Optional[List[Checkpoint]]:
    if not q.checkpoints_json:
        return None
    return [Checkpoint(c.get("statement"), c["label"]) for c in json.loads(q.checkpoints_json)]


# ── building ─────────────────────────────────────────────────────────────────
def prepare(schema_sql: str, data_sql: str, model_answer: str, *, checkpoints=None,
            bag: bool = False, suite_json: Optional[dict] = None) -> PreparedQuestion:
    """Validate a question's content and build (or load) its test databases.
    Raises QuestionInputError naming the field that is wrong."""
    try:
        Database.from_sql(schema_sql)
    except RAError as e:
        raise QuestionInputError("schema", e)
    if data_sql and data_sql.strip():
        try:
            Database.from_sql(schema_sql, data_sql)
        except RAError as e:
            raise QuestionInputError("data", e)
    try:
        question = PreparedQuestion(schema_sql, model_answer, data_sql or "", options=eval_options(),
                                    bag=bag, checkpoints=checkpoints, suite_json=suite_json)
    except RAError as e:
        raise QuestionInputError("model_answer", e)
    for cp in question.checkpoints:
        try:
            question._checkpoint_index(cp)
        except ValueError as e:
            raise QuestionInputError("checkpoints", RAError("RA012", str(e)))
    return question


def apply_content(q: RAQuestion, *, schema_sql: str, data_sql: str, model_answer: str,
                  checkpoints: Optional[List[dict]], compare_bags: bool) -> PreparedQuestion:
    """Set a question's graded content, rebuilding its test databases only if needed."""
    checkpoints_json = json.dumps(checkpoints) if checkpoints else None
    unchanged = (q.suite_json is not None and q.schema_sql == schema_sql and (q.data_sql or "") == (data_sql or "")
                 and q.model_answer == model_answer and bool(q.compare_bags) == compare_bags)
    cps = [Checkpoint(c.get("statement"), c["label"]) for c in checkpoints] if checkpoints else None
    prepared = prepare(schema_sql, data_sql, model_answer, checkpoints=cps, bag=compare_bags,
                       suite_json=json.loads(q.suite_json) if unchanged else None)
    q.schema_sql, q.data_sql, q.model_answer = schema_sql, data_sql or "", model_answer
    q.checkpoints_json = checkpoints_json
    q.compare_bags = int(compare_bags)
    if not unchanged:
        q.suite_json = json.dumps(prepared.suite.to_json())
        q.suite_summary_json = json.dumps(prepared.suite.summary())
    return prepared


def prepared_for(q: RAQuestion) -> PreparedQuestion:
    """The stored question, ready to grade (cached; rebuilt only if the row changed)."""
    key = ("question", q.id, str(q.updated_at), q.checkpoints_json, eval_options())
    return grading.cached(key, lambda: prepare(
        q.schema_sql, q.data_sql, q.model_answer, checkpoints=checkpoints_of(q), bag=bool(q.compare_bags),
        suite_json=json.loads(q.suite_json) if q.suite_json else None))


# ── access ───────────────────────────────────────────────────────────────────
def visible_to(q: RAQuestion, user: User) -> bool:
    if q.is_deleted:
        return False
    if is_staff(user):
        return True
    # Assessment clones are reached through their assessment (step 5), never directly.
    return bool(q.is_published) and q.owner_assessment_id is None


def bank_questions(db: Session, user: User) -> List[RAQuestion]:
    query = db.query(RAQuestion).filter(RAQuestion.is_deleted == 0, RAQuestion.owner_assessment_id.is_(None))
    if not is_staff(user):
        query = query.filter(RAQuestion.is_published == 1)
    return query.order_by(RAQuestion.id).all()


def progress_by_question(db: Session, user: User) -> dict:
    """{question_id: (attempts, solved)} for this user."""
    rows = (db.query(RAAttempt.question_id, func.count(RAAttempt.id), func.max(RAAttempt.is_correct))
            .filter(RAAttempt.user_id == user.id).group_by(RAAttempt.question_id).all())
    return {qid: (count, bool(solved)) for qid, count, solved in rows}


# ── what a student sees ──────────────────────────────────────────────────────
def relations_for(q: RAQuestion) -> List[dict]:
    """The schema (and data, if the question has any) as students see it."""
    return Database.from_sql(q.schema_sql, q.data_sql or "").to_dict()


def check(q: RAQuestion, answer: str) -> Tuple[dict, str, List[dict]]:
    """Evaluate an answer without grading it: on the question's data, or else on a
    generated example database. Returns (result, source, relations); raises RAError."""
    prepared = prepared_for(q)
    db, source = grading.structure_database(prepared)
    result = evaluate(parse(answer, db.names()), db, options=eval_options())
    return ({"columns": result.columns, "rows": [list(r) for r in result.rows], "row_count": len(result.rows),
             "steps": result.statements, "warnings": [w.to_dict() for w in result.warnings]},
            source, db.to_dict())


@dataclass
class Submission:
    attempt: RAAttempt
    result: GradeResult


def submit(db: Session, user: User, q: RAQuestion, answer: str) -> Submission:
    """Grade an answer and record the attempt (always, correct or not)."""
    result = prepared_for(q).grade(answer)
    attempt = RAAttempt(user_id=user.id, question_id=q.id, answer=answer, verdict=result.verdict,
                        is_correct=int(result.correct), method=result.method,
                        result_json=json.dumps(result.to_dict(), default=str),
                        elapsed_ms=int(result.elapsed_ms))
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return Submission(attempt, result)


def for_student(q: RAQuestion, result: GradeResult) -> Optional[dict]:
    """The grade a student may see, given the question's feedback switches."""
    if q.hide_correctness:
        return None
    data = result.to_dict()
    if not q.show_step_direction:
        for step in data["steps"]:
            step.update(status="none", checkpoint=None, renamed=False, case=None)
    return data


def history(db: Session, user: User, q: RAQuestion, limit: int = 50) -> List[RAAttempt]:
    return (db.query(RAAttempt).filter(RAAttempt.user_id == user.id, RAAttempt.question_id == q.id)
            .order_by(RAAttempt.created_at.desc(), RAAttempt.id.desc()).limit(limit).all())
