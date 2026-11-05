"""Regrade a question's past attempts with the current grader, when staff ask for it.

The grader improves (task 4 added proofs on every valid database), and a better grader
can change a verdict: an answer once marked wrong by a counterexample that broke a
foreign key is now proved right. Nothing changes by itself. Staff press "Regrade" on the
question's analytics page and first see what *would* change (``preview``), then save it
(``apply``). Marks given by hand (overrides) are always kept: the override still decides.

``preview`` works in batches (``BATCH_SECONDS``), so a large class never makes one
request run for minutes; the page asks for the next batch until it is done. The same
answer to the same part is graded once per batch. ``apply`` grades only the attempts it
is given again (the grader is deterministic, so the result is what the preview showed)
and saves them.
"""
import json
import time
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.core.ra.step_marking import mark
from app.models.ra_attempt import RAAttempt
from app.models.ra_question import RAQuestion
from app.models.ra_question_part import RAQuestionPart
from app.models.user import User
from app.services.ra import multi_step, questions as svc

BATCH_SECONDS = 15.0
MAX_APPLY = 2000


def _parts(db: Session, q: RAQuestion) -> Dict[int, RAQuestionPart]:
    return {p.id: p for p in db.query(RAQuestionPart)
            .filter(RAQuestionPart.question_id == q.id, RAQuestionPart.is_deleted == 0).all()}


def _grade(q: RAQuestion, part: RAQuestionPart, a: RAAttempt) -> dict:
    """What the current grader records for this attempt (the same fields Submit stores)."""
    steps = multi_step.steps_of(part)
    if a.step_answers_json and steps:
        answers = multi_step.padded(steps, json.loads(a.step_answers_json))
        marking = mark(svc.prepared_for(q, part), steps, answers)
        result = marking.grade.to_dict()
        result.update(marking=marking.to_dict(), statement_boxes=marking.statement_boxes)
        return dict(verdict=marking.grade.verdict, is_correct=int(marking.grade.correct),
                    method=marking.grade.method, result_json=json.dumps(result, default=str),
                    marks_earned=marking.earned)
    result = svc.prepared_for(q, part).grade(a.answer)
    return dict(verdict=result.verdict, is_correct=int(result.correct), method=result.method,
                result_json=json.dumps(result.to_dict(), default=str), marks_earned=None)


def _key(a: RAAttempt) -> Tuple:
    return (a.part_id, a.step_answers_json or "", a.answer)


def _changed(a: RAAttempt, new: dict) -> bool:
    return (a.verdict != new["verdict"] or int(a.is_correct or 0) != new["is_correct"]
            or (a.method or None) != new["method"] or a.marks_earned != new["marks_earned"])


def preview(db: Session, q: RAQuestion, after_id: Optional[int] = None) -> dict:
    """The next batch: every attempt whose verdict, marks or method would change."""
    parts = _parts(db, q)
    query = db.query(RAAttempt).filter(RAAttempt.question_id == q.id, RAAttempt.part_id.in_(list(parts) or [-1]))
    total = query.count()
    done_before = query.filter(RAAttempt.id <= after_id).count() if after_id is not None else 0
    rows = (query.filter(RAAttempt.id > after_id) if after_id is not None else query).order_by(RAAttempt.id.asc()).all()
    users = {u.id: u for u in db.query(User).filter(User.id.in_({a.user_id for a in rows} or {-1})).all()}
    started = time.monotonic()
    cache: Dict[Tuple, dict] = {}
    changes: List[dict] = []
    last_id, checked = after_id, 0
    for a in rows:
        if checked and time.monotonic() - started > BATCH_SECONDS:
            break
        key = _key(a)
        if key not in cache:
            cache[key] = _grade(q, parts[a.part_id], a)
        new = cache[key]
        checked += 1
        last_id = a.id
        if not _changed(a, new):
            continue
        u = users.get(a.user_id)
        changes.append({
            "attempt_id": a.id, "part_id": a.part_id, "user_id": a.user_id,
            "student": (u.name or u.email) if u else "", "email": u.email if u else "",
            "answer": a.answer, "created_at": a.created_at.isoformat() if a.created_at else None,
            "old": {"verdict": a.verdict, "correct": bool(a.is_correct), "method": a.method,
                    "marks_earned": a.marks_earned},
            "new": {"verdict": new["verdict"], "correct": bool(new["is_correct"]), "method": new["method"],
                    "marks_earned": new["marks_earned"]},
            "verdict_changed": a.verdict != new["verdict"] or a.marks_earned != new["marks_earned"],
            "overridden": a.override_is_correct is not None,
        })
    return {"total": total, "checked": done_before + checked, "after_id": last_id,
            "done": done_before + checked >= total, "changes": changes}


def apply(db: Session, q: RAQuestion, attempt_ids: Sequence[int]) -> int:
    """Regrade these attempts and save them; how many changed. Overrides are kept."""
    parts = _parts(db, q)
    ids = list(dict.fromkeys(attempt_ids))[:MAX_APPLY]
    rows = (db.query(RAAttempt).filter(RAAttempt.question_id == q.id, RAAttempt.id.in_(ids or [-1]),
                                       RAAttempt.part_id.in_(list(parts) or [-1])).all())
    cache: Dict[Tuple, dict] = {}
    changed = 0
    for a in rows:
        key = _key(a)
        if key not in cache:
            cache[key] = _grade(q, parts[a.part_id], a)
        new = cache[key]
        if not _changed(a, new):
            continue
        a.verdict, a.is_correct, a.method = new["verdict"], new["is_correct"], new["method"]
        a.result_json, a.marks_earned = new["result_json"], new["marks_earned"]
        changed += 1
    db.commit()
    return changed
