"""Relational-algebra questions: saving, what each role may see, grading and attempts.

Saving a question validates it fully before anything is stored: the schema and data must
load, the model answer must run, and every checkpoint must name a step of the model
answer. Its test databases are then built once (core/ra/suite.py) and stored with it, so
every student is graded on exactly the same databases, and editing the schema, data or
model answer rebuilds them.

A question has one or more parts (ra_question_parts): one schema and data, and for each
part its own text, model answer, checkpoints, marks and test databases. Students check
and submit one part at a time; a question is solved when every part is.

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
from app.models.ra_question_part import RAQuestionPart
from app.models.user import User, UserRole
from app.services.ra import assessment as ra_assessment, grading


class QuestionInputError(Exception):
    """A staff input that cannot be saved; ``source`` says which field, ``part`` which
    part (its index in the form) for a model answer or checkpoints."""

    def __init__(self, source: str, error: RAError, part: Optional[int] = None):
        super().__init__(error.message)
        self.source = source
        self.error = error
        self.part = part


class PartNotFound(Exception):
    """The answer names no part of this question (or none, when it has several)."""


def eval_options() -> EvalOptions:
    return EvalOptions(aggregate_nulls=settings.RA_AGGREGATE_NULLS)


def is_staff(user: User) -> bool:
    return user.role in (UserRole.STAFF, UserRole.ADMIN)


def checkpoints_of(part: RAQuestionPart) -> Optional[List[Checkpoint]]:
    if not part.checkpoints_json:
        return None
    return [Checkpoint(c.get("statement"), c["label"]) for c in json.loads(part.checkpoints_json)]


def parts_of(db: Session, q: RAQuestion) -> List[RAQuestionPart]:
    return (db.query(RAQuestionPart).filter(RAQuestionPart.question_id == q.id, RAQuestionPart.is_deleted == 0)
            .order_by(RAQuestionPart.position, RAQuestionPart.id).all())


def part_for(db: Session, q: RAQuestion, part_id: Optional[int]) -> RAQuestionPart:
    """The part an answer is for. ``None`` is allowed only when the question has one part."""
    parts = parts_of(db, q)
    if part_id is None:
        if len(parts) == 1:
            return parts[0]
        raise PartNotFound("Say which part of the question this answer is for.")
    for part in parts:
        if part.id == part_id:
            return part
    raise PartNotFound("This part of the question does not exist.")


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
            question.checkpoint_index(cp)
        except ValueError as e:
            raise QuestionInputError("checkpoints", RAError("RA012", str(e)))
    return question


def save_content(db: Session, q: RAQuestion, *, schema_sql: str, data_sql: str, parts: List[dict],
                 compare_bags: bool) -> List[PreparedQuestion]:
    """Set a question's graded content: its schema, data and parts. ``parts`` are dicts
    with label, description, marks, model_answer, checkpoints and, for a part that
    already exists, its id. Every part is validated before anything changes; a part's
    test databases are rebuilt only if its model answer, the schema, the data or the
    set/bag choice changed. Parts left out are deleted. ``q`` must have an id."""
    if not parts:
        raise QuestionInputError("model_answer", RAError("RA012", "A question needs at least one part."), 0)
    existing = {p.id: p for p in parts_of(db, q)} if q.id is not None else {}
    same_tables = (q.schema_sql == schema_sql and (q.data_sql or "") == (data_sql or "")
                   and bool(q.compare_bags) == compare_bags)
    plan = []
    for index, spec in enumerate(parts):
        row = existing.get(spec.get("id")) if spec.get("id") is not None else None
        reuse = (row is not None and same_tables and row.suite_json is not None
                 and row.model_answer == spec["model_answer"])
        cps = [Checkpoint(c.get("statement"), c["label"]) for c in spec["checkpoints"]] if spec.get("checkpoints") else None
        try:
            prepared = prepare(schema_sql, data_sql, spec["model_answer"], checkpoints=cps, bag=compare_bags,
                               suite_json=json.loads(row.suite_json) if reuse else None)
        except QuestionInputError as e:
            if e.source in ("model_answer", "checkpoints"):
                e.part = index
            raise
        plan.append((spec, row, reuse, prepared))

    q.schema_sql, q.data_sql = schema_sql, data_sql or ""
    q.compare_bags = int(compare_bags)
    # The question's own model-answer columns predate parts; keep them equal to part 1.
    first = parts[0]
    q.model_answer = first["model_answer"]
    q.checkpoints_json = json.dumps(first["checkpoints"]) if first.get("checkpoints") else None
    q.suite_json = q.suite_summary_json = None

    kept = set()
    for position, (spec, row, reuse, prepared) in enumerate(plan):
        if row is None:
            row = RAQuestionPart(question_id=q.id, is_deleted=0)
            db.add(row)
        row.position = position
        row.label = (spec.get("label") or "").strip()
        row.description = spec.get("description") or ""
        row.marks = int(spec.get("marks") or 1)
        row.model_answer = spec["model_answer"]
        row.checkpoints_json = json.dumps(spec["checkpoints"]) if spec.get("checkpoints") else None
        if not reuse:
            row.suite_json = json.dumps(prepared.suite.to_json())
            row.suite_summary_json = json.dumps(prepared.suite.summary())
        if row.id is not None:
            kept.add(row.id)
    for part_id, row in existing.items():
        if part_id not in kept:
            row.is_deleted = 1
    return [prepared for _spec, _row, _reuse, prepared in plan]


def prepared_for(q: RAQuestion, part: RAQuestionPart) -> PreparedQuestion:
    """A stored part, ready to grade (cached; rebuilt only if the part or question changed)."""
    key = ("part", part.id, str(part.updated_at), str(q.updated_at), part.checkpoints_json,
           bool(q.compare_bags), eval_options())
    return grading.cached(key, lambda: prepare(
        q.schema_sql, q.data_sql, part.model_answer, checkpoints=checkpoints_of(part), bag=bool(q.compare_bags),
        suite_json=json.loads(part.suite_json) if part.suite_json else None))


# ── access ───────────────────────────────────────────────────────────────────
def visible_to(db: Session, q: RAQuestion, user: User) -> bool:
    if q.is_deleted:
        return False
    if is_staff(user):
        return True
    if q.owner_assessment_id is not None:
        # An assessment's copy: only while the student is taking that assessment.
        return ra_assessment.accessible_via_assessment(db, q, user)
    return bool(q.is_published)


def bank_questions(db: Session, user: User) -> List[RAQuestion]:
    query = db.query(RAQuestion).filter(RAQuestion.is_deleted == 0, RAQuestion.owner_assessment_id.is_(None))
    if not is_staff(user):
        query = query.filter(RAQuestion.is_published == 1)
    return query.order_by(RAQuestion.id).all()


def part_progress(db: Session, user: User) -> dict:
    """{part_id: (attempts, solved)} for this user."""
    rows = (db.query(RAAttempt.part_id, func.count(RAAttempt.id), func.max(RAAttempt.is_correct))
            .filter(RAAttempt.user_id == user.id).group_by(RAAttempt.part_id).all())
    return {pid: (count, bool(solved)) for pid, count, solved in rows}


@dataclass
class Progress:
    attempts: int
    parts_total: int
    parts_solved: int

    @property
    def solved(self) -> bool:
        return self.parts_total > 0 and self.parts_solved == self.parts_total


def progress_by_question(db: Session, user: User, question_ids: List[int]) -> dict:
    """{question_id: Progress} for this user."""
    if not question_ids:
        return {}
    by_part = part_progress(db, user)
    out = {qid: Progress(0, 0, 0) for qid in question_ids}
    for pid, qid in (db.query(RAQuestionPart.id, RAQuestionPart.question_id)
                     .filter(RAQuestionPart.question_id.in_(question_ids), RAQuestionPart.is_deleted == 0)):
        attempts, solved = by_part.get(pid, (0, False))
        p = out[qid]
        p.attempts += attempts
        p.parts_total += 1
        p.parts_solved += int(solved)
    return out


# ── what a student sees ──────────────────────────────────────────────────────
def relations_for(q: RAQuestion) -> List[dict]:
    """The schema (and data, if the question has any) as students see it."""
    return Database.from_sql(q.schema_sql, q.data_sql or "").to_dict()


def check(q: RAQuestion, part: RAQuestionPart, answer: str) -> Tuple[dict, str, List[dict]]:
    """Evaluate an answer without grading it: on the question's data, or else on a
    generated example database. Returns (result, source, relations); raises RAError."""
    prepared = prepared_for(q, part)
    db, source = grading.structure_database(prepared)
    result = evaluate(parse(answer, db.names()), db, options=eval_options())
    return ({"columns": result.columns, "rows": [list(r) for r in result.rows], "row_count": len(result.rows),
             "steps": result.statements, "warnings": [w.to_dict() for w in result.warnings]},
            source, db.to_dict())


@dataclass
class Submission:
    attempt: RAAttempt
    result: GradeResult


def submit(db: Session, user: User, q: RAQuestion, part: RAQuestionPart, answer: str) -> Submission:
    """Grade an answer to one part and record the attempt (always, correct or not). In an
    assessment, the attempt must still be running and have Submits left (403 otherwise)."""
    ra_assessment.guard_submit(db, q, part, user, is_staff(user))
    result = prepared_for(q, part).grade(answer)
    attempt = RAAttempt(user_id=user.id, question_id=q.id, part_id=part.id, answer=answer, verdict=result.verdict,
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


def submission_counts(db: Session, user: User, q: RAQuestion, part: RAQuestionPart) -> Tuple[Optional[int], int]:
    """(maximum Submits, Submits used) for one part — the maximum is None outside
    assessments or uncapped. In an assessment each part has the item's maximum."""
    return ra_assessment.submission_limit(db, q), ra_assessment.submissions_used(db, part, user)


def history(db: Session, user: User, q: RAQuestion, limit: int = 50) -> List[RAAttempt]:
    return (db.query(RAAttempt).filter(RAAttempt.user_id == user.id, RAAttempt.question_id == q.id)
            .order_by(RAAttempt.created_at.desc(), RAAttempt.id.desc()).limit(limit).all())
