"""The question type (mixed / final answer / multi-step) when staff save or switch it.

See core/ra/answer_format.py for the three types. Here:
  * ``part_spec``: before a part is saved, check it fits the question's type, and for a
    multi-step part build its model answer and checkpoints from its steps;
  * ``convert``: the staff form's type switch, which rewrites every part's model answer
    into the new type (nothing is saved; staff can edit the result);
  * ``locked``: once any student has submitted to a question, its type can no longer
    change, since their marks were given under the old one (staff trying the question
    out don't count).
"""
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.ra import Database, RAError
from app.core.ra import errors as E
from app.core.ra.answer_format import (FINAL_ANSWER, MAX_STEPS, MIN_STEPS, MIXED, MULTI_STEP, STEP_NAME, Step,
                                       default_step_name, join, single_expression, split, steps_checkpoints,
                                       steps_from_json, steps_program)
from app.core.ra.step_marking import Boxes
from app.models.ra_attempt import RAAttempt
from app.models.ra_question import RAQuestion
from app.models.user import User, UserRole

FORMAT_NAMES = {MIXED: "Mixed", FINAL_ANSWER: "Final answer", MULTI_STEP: "Multi-step"}


class FormatError(Exception):
    """A part that doesn't fit the question's type: which field, part and step."""

    def __init__(self, source: str, error: RAError, part: Optional[int] = None, step: Optional[int] = None):
        super().__init__(error.message)
        self.source, self.error, self.part, self.step = source, error, part, step


def _error(message: str) -> RAError:
    return RAError(E.INVALID_ASSIGNMENT, message)


def locked(db: Session, q: RAQuestion) -> bool:
    return q.id is not None and (db.query(RAAttempt.id).join(User, User.id == RAAttempt.user_id)
                                 .filter(RAAttempt.question_id == q.id, User.role == UserRole.STUDENT)
                                 .first()) is not None


def check_change(db: Session, q: RAQuestion, answer_format: str) -> None:
    if q.id is not None and (q.answer_format or MIXED) != answer_format and locked(db, q):
        raise FormatError("answer_format", _error(
            f"This question has been answered already, so its type can't change from "
            f"{FORMAT_NAMES[q.answer_format or MIXED]} to {FORMAT_NAMES[answer_format]}. "
            f"Make a copy of the question to use another type."))


def part_spec(answer_format: str, spec: dict, index: int, schema: Database, options) -> dict:
    """The part as it will be saved under this type. Raises FormatError."""
    if answer_format == MULTI_STEP:
        return _multi_step_spec(spec, index, schema, options)
    spec = dict(spec, steps=None)
    if answer_format == FINAL_ANSWER and (spec.get("model_answer") or "").strip():
        try:
            single_expression(spec["model_answer"], schema.names())
        except RAError as e:
            if e.code == E.INVALID_ASSIGNMENT:
                raise FormatError("model_answer", _error(
                    "This is a Final answer question, so the model answer must be one expression, "
                    "without steps (R1 := …)."), index)
            # any other error is reported by the usual check of the model answer
        spec["checkpoints"] = None
    return spec


def _multi_step_spec(spec: dict, index: int, schema: Database, options) -> dict:
    steps = steps_from_json(spec.get("steps") or [])
    if not MIN_STEPS <= len(steps) <= MAX_STEPS:
        raise FormatError("steps", _error(f"A multi-step part needs {MIN_STEPS} to {MAX_STEPS} steps "
                                          f"(it has {len(steps)})."), index)
    relations = {t.name.casefold() for t in schema.tables}
    seen = set()
    for k, s in enumerate(steps):
        if not s.prompt.strip():
            raise FormatError("steps", _error("Every step needs a prompt: it tells students what the box is for."),
                              index, k)
        if s.marks < 0:
            raise FormatError("steps", _error("A step's marks can't be negative."), index, k)
        if k == len(steps) - 1:
            continue
        s.name = (s.name or "").strip() or default_step_name(k)
        if not STEP_NAME.match(s.name):
            raise FormatError("steps", _error(f"“{s.name}” can't be a step name: use letters, digits and _, "
                                              f"starting with a letter (e.g. R1, CE_Courses)."), index, k)
        if s.name.casefold() in relations:
            raise FormatError("steps", _error(f"{s.name} is already a relation of the schema; "
                                              f"give the step another name."), index, k)
        if s.name.casefold() in seen:
            raise FormatError("steps", _error(f"Two steps are called {s.name}."), index, k)
        seen.add(s.name.casefold())
    total = sum(s.marks for s in steps)
    if not 1 <= total <= 100:
        raise FormatError("steps", _error(f"The steps' marks add up to {total}; the part needs 1 to 100."), index)
    boxes = Boxes(schema, options, steps, [s.model_answer for s in steps])
    for k, (s, box) in enumerate(zip(steps, boxes.results)):
        if box.status == "empty":
            raise FormatError("steps", _error("Write this step's model answer."), index, k)
        if box.status == "error":
            err = box.error
            raise FormatError("steps", RAError(err["code"], err["message"], err.get("line"), err.get("col"),
                                               hint=err.get("hint")), index, k)
    return dict(spec, steps=[s.to_dict() for s in steps], model_answer=steps_program(steps),
                checkpoints=steps_checkpoints(steps), marks=total)


# ── the type switch in the staff form ────────────────────────────────────────
def convert(schema_sql: str, from_format: str, to_format: str, parts: List[dict]) -> List[dict]:
    """Every part rewritten for the new type: [{model_answer, checkpoints, steps, marks,
    error}] in the same order. A part that can't be read keeps its text (as one step,
    for multi-step) with ``error`` saying why, for staff to rewrite by hand."""
    names = Database.from_sql(schema_sql).names()        # RAError for a broken schema
    return [_convert_part(names, from_format, to_format, p) for p in parts]


def _convert_part(names, from_format: str, to_format: str, part: dict) -> dict:
    marks = int(part.get("marks") or 1)
    if from_format == MULTI_STEP and part.get("steps"):
        steps = steps_from_json(part["steps"])
        for k, s in enumerate(steps[:-1]):
            s.name = (s.name or "").strip() or default_step_name(k)
        model_answer = steps_program(steps)
        checkpoints = steps_checkpoints(steps)
        marks = max(1, sum(s.marks for s in steps))
    else:
        model_answer = part.get("model_answer") or ""
        checkpoints = part.get("checkpoints")
    out = dict(model_answer=model_answer, checkpoints=checkpoints, steps=None, marks=marks, error=None)
    if to_format == from_format:
        return dict(out, steps=part.get("steps") if to_format == MULTI_STEP else None)
    if to_format == MIXED:
        return out
    if not model_answer.strip():
        if to_format == MULTI_STEP:
            out["steps"] = [Step(default_step_name(0), "", 0, "").to_dict(), Step(None, "", marks, "").to_dict()]
        return dict(out, checkpoints=None)
    try:
        if to_format == FINAL_ANSWER:
            return dict(out, model_answer=join(model_answer, names), checkpoints=None)
        out["steps"] = [s.to_dict() for s in split(model_answer, names, checkpoints, marks)]
        return dict(out, checkpoints=None)
    except RAError as e:
        message = f"Couldn't convert this model answer automatically ({e.message}); please rewrite it by hand."
        if to_format == MULTI_STEP:
            out["steps"] = [Step(None, "", marks, model_answer).to_dict()]
        return dict(out, error=message)
