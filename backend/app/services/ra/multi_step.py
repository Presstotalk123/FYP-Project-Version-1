"""Students answering a multi-step question: one box per step (core/ra/step_marking.py).

  * ``check``: every box run on the data shown with the question (not graded, not
    recorded), for each box's Show structure.
  * ``submit``: the boxes marked and recorded as one attempt. ``answer`` keeps them
    joined as R1 := … lines (for history and analytics), ``step_answers_json`` the boxes
    themselves, ``marks_earned`` the marks.
  * ``step_results``: what the student sees after Submit, per step: its marks and how
    they were earned, the box's error, how it compares with the model's steps (✓/◐/○,
    under the question's switch), and, for a step that earned nothing, the box's table
    next to the model step's on the shown data.
"""
import json
from typing import List, Optional, Sequence, Tuple

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.ra import Database, RAError, evaluate
from app.core.ra.answer_format import Step, steps_from_json
from app.core.ra.grader import PreparedQuestion
from app.core.ra.step_marking import Boxes, StepMarking, mark
from app.models.ra_attempt import RAAttempt
from app.models.ra_question import RAQuestion
from app.models.ra_question_part import RAQuestionPart
from app.models.user import User
from app.services.ra import assessment as ra_assessment, grading, questions as svc


def steps_of(part: RAQuestionPart) -> List[Step]:
    return steps_from_json(json.loads(part.steps_json)) if part.steps_json else []


def public_steps(part: RAQuestionPart) -> List[dict]:
    """The steps as students see them: never their model answers."""
    return [dict(name=s.name, prompt=s.prompt, marks=s.marks) for s in steps_of(part)]


def padded(steps: Sequence[Step], answers: Sequence[str]) -> List[str]:
    answers = [a or "" for a in answers][:len(steps)]
    return answers + [""] * (len(steps) - len(answers))


def joined(steps: Sequence[Step], answers: Sequence[str]) -> str:
    """The boxes as one text, R1 := … lines then the final step (empty boxes left out)."""
    lines = []
    for s, a in zip(steps, answers):
        if a.strip():
            lines.append(f"{s.name} := {a.strip()}" if s.name else a.strip())
    return "\n".join(lines)


def _run_boxes(schema: Database, options, steps: Sequence[Step], answers: Sequence[str],
               db: Database) -> Tuple[Boxes, List[Optional[dict]]]:
    """The boxes read, and each working box's evaluated step ({name, tree}) on ``db``."""
    boxes = Boxes(schema, options, steps, answers)
    trees: List[Optional[dict]] = [None] * len(steps)
    program = boxes.program()
    if program is not None:
        try:
            statements = evaluate(program, db, options=options).statements
            for (k, _s), statement in zip(boxes.statements, statements):
                trees[k] = statement
        except RAError:
            pass                  # each box was checked on the empty schema; nothing to show
    return boxes, trees


def _shown(q: RAQuestion, part: RAQuestionPart) -> Tuple[Database, str]:
    db, source = svc.shown_database(q)
    if db is None:
        db, source = grading.structure_database(svc.prepared_for(q, part))
    return db, source


def check(q: RAQuestion, part: RAQuestionPart, answers: Sequence[str]) -> dict:
    """Each box on the shown data: {source, boxes: [{status, error, step}]}."""
    steps = steps_of(part)
    answers = padded(steps, answers)
    db, source = _shown(q, part)
    boxes, trees = _run_boxes(Database.from_sql(q.schema_sql), svc.eval_options(), steps, answers, db)
    return {"source": source,
            "boxes": [dict(status=b.status, error=b.error, step=t) for b, t in zip(boxes.results, trees)]}


def submit(db: Session, user: User, q: RAQuestion, part: RAQuestionPart, answers: Sequence[str]
           ) -> Tuple[RAAttempt, StepMarking]:
    steps = steps_of(part)
    answers = padded(steps, answers)
    if not any(a.strip() for a in answers):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Write at least one step before submitting.")
    ra_assessment.guard_submit(db, q, part, user, svc.is_staff(user))
    marking = mark(svc.prepared_for(q, part), steps, answers)
    result = marking.grade.to_dict()
    result.update(marking=marking.to_dict(), statement_boxes=marking.statement_boxes)
    attempt = RAAttempt(user_id=user.id, question_id=q.id, part_id=part.id, answer=joined(steps, answers),
                        verdict=marking.grade.verdict, is_correct=int(marking.grade.correct),
                        method=marking.grade.method, result_json=json.dumps(result, default=str),
                        elapsed_ms=int(marking.grade.elapsed_ms),
                        step_answers_json=json.dumps(answers), marks_earned=marking.earned)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt, marking


def step_results(prepared: PreparedQuestion, steps: Sequence[Step], answers: Sequence[str],
                 marking: StepMarking, shown_db: Optional[Database], direction: bool) -> List[dict]:
    """Per step, what the student sees after Submit (see the module notes)."""
    answers = padded(steps, answers)
    feedback = [None] * len(steps)
    for statement, box in enumerate(marking.statement_boxes):
        if statement < len(marking.grade.steps):
            fb = marking.grade.steps[statement].to_dict()
            if not direction:
                fb.update(status="none", checkpoint=None, renamed=False, case=None)
            feedback[box] = fb
    trees: List[Optional[dict]] = [None] * len(steps)
    model_steps = None
    if shown_db is not None:
        _boxes, trees = _run_boxes(prepared.schema, prepared.options, steps, answers, shown_db)
        try:
            model_steps = evaluate(prepared.model, shown_db, trace=False, options=prepared.options).step_relations
        except RAError:
            model_steps = None
    out = []
    for j, (m, box) in enumerate(zip(marking.steps, marking.boxes)):
        row = dict(m.to_dict(), box_status=box.status, box_error=box.error, feedback=feedback[j],
                   structure=trees[j], student=None, expected=None)
        if m.status == "missed" and model_steps is not None and j < len(model_steps):
            rel = model_steps[j][2]
            row["expected"] = {"columns": rel.labels, "rows": [list(r) for r in rel.rows]}
            tree = (trees[j] or {}).get("tree")
            if tree:
                row["student"] = {"columns": tree["columns"], "rows": tree["rows"]}
        out.append(row)
    return out


def results_for(q: RAQuestion, part: RAQuestionPart, answers: Sequence[str], marking: StepMarking,
                staff: bool) -> Tuple[List[dict], Optional[str]]:
    """``step_results`` for a stored question, on the data shown with it."""
    db, source = _shown(q, part)
    rows = step_results(svc.prepared_for(q, part), steps_of(part), answers, marking, db,
                        direction=staff or bool(q.show_step_direction))
    return rows, source
