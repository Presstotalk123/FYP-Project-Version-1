"""Staff analytics over RA attempts: who practised, what they solved, and where they go wrong.

Computed live on each request, like sql_analytics.py (class sizes are small and staff want
fresh numbers), but without the shared cache namespace, so the shared cache module stays
untouched. Students only: staff test attempts never count.

RA has something SQL analytics does not: every attempt keeps the grader's verdict
(wrong columns, wrong on the data, wrong on some generated database, unreadable) and, for
an unreadable answer, its error code. So besides solved/attempts, staff see which kind of
mistake each part draws, and which errors are most common.

A part is solved when any attempt at it counts as correct: graded correct, or overridden
to correct by staff (``assessment._EFFECTIVE_CORRECT``). Verdict counts use the grader's
own verdict, since an override is a marking decision, not a different mistake.
"""
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.ra_attempt import RAAttempt
from app.models.ra_question import RAQuestion
from app.models.ra_question_part import RAQuestionPart
from app.models.user import User, UserRole
from app.services.ra.assessment import _EFFECTIVE_CORRECT

VERDICTS = ["correct", "wrong_columns", "wrong_result", "wrong_in_general", "invalid_expression"]
_TOP_ERRORS = 8


@dataclass
class _Attempt:
    id: int
    user_id: int
    question_id: int
    part_id: Optional[int]
    verdict: str
    correct: bool
    created_at: object
    error: Optional[dict]


def class_groups(db: Session) -> List[str]:
    rows = (db.query(User.class_group).filter(User.class_group.isnot(None), User.class_group != "")
            .distinct().order_by(User.class_group.asc()).all())
    return [r[0] for r in rows]


def _students(db: Session, class_group: Optional[str]) -> Dict[int, dict]:
    q = db.query(User.id, User.email, User.name, User.class_group).filter(User.role == UserRole.STUDENT)
    if class_group:
        q = q.filter(User.class_group == class_group)
    return {uid: {"email": email or "", "name": name, "class_group": group} for uid, email, name, group in q.all()}


def _attempts(db: Session, question_ids: List[int], user_ids: List[int]) -> List[_Attempt]:
    if not question_ids or not user_ids:
        return []
    rows = (db.query(RAAttempt.id, RAAttempt.user_id, RAAttempt.question_id, RAAttempt.part_id, RAAttempt.verdict,
                     _EFFECTIVE_CORRECT, RAAttempt.created_at, RAAttempt.result_json)
            .filter(RAAttempt.question_id.in_(question_ids), RAAttempt.user_id.in_(user_ids))
            .order_by(RAAttempt.created_at.asc(), RAAttempt.id.asc()).all())
    return [_Attempt(i, u, q, p, v, bool(c), t, _error(v, rj)) for i, u, q, p, v, c, t, rj in rows]


def _error(verdict: str, result_json: Optional[str]) -> Optional[dict]:
    if verdict != "invalid_expression" or not result_json:
        return None
    try:
        return (json.loads(result_json) or {}).get("error")
    except (TypeError, ValueError):
        return None


def _parts(db: Session, question_ids: List[int]) -> List[RAQuestionPart]:
    if not question_ids:
        return []
    return (db.query(RAQuestionPart)
            .filter(RAQuestionPart.question_id.in_(question_ids), RAQuestionPart.is_deleted == 0)
            .order_by(RAQuestionPart.question_id, RAQuestionPart.position, RAQuestionPart.id).all())


def _verdicts(attempts) -> Dict[str, int]:
    counts = Counter(a.verdict for a in attempts)
    return {v: counts.get(v, 0) for v in VERDICTS}


def _top_errors(attempts) -> List[dict]:
    """The commonest error codes among unreadable answers, each with an example message."""
    by_code: Dict[str, dict] = {}
    for a in attempts:
        if not a.error:
            continue
        code = a.error.get("code") or "?"
        e = by_code.setdefault(code, {"code": code, "example": a.error.get("message") or "", "count": 0,
                                      "_students": set()})
        e["count"] += 1
        e["_students"].add(a.user_id)
    out = sorted(by_code.values(), key=lambda e: e["count"], reverse=True)[:_TOP_ERRORS]
    return [{**{k: v for k, v in e.items() if k != "_students"}, "students": len(e["_students"])} for e in out]


def _submits_to_correct(attempts) -> Optional[int]:
    """Attempts up to and including the first correct one (chronological), or None."""
    for i, a in enumerate(attempts, 1):
        if a.correct:
            return i
    return None


def _mean(values: List[int]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


def _iso(t) -> Optional[str]:
    return t.isoformat() if t else None


def _part_label(part: RAQuestionPart, index: int, count: int) -> str:
    return part.label.strip() if part.label and part.label.strip() else ("" if count == 1 else f"Part {index + 1}")


# ── the class ────────────────────────────────────────────────────────────────
def class_analytics(db: Session, class_group: Optional[str] = None) -> dict:
    """Every practice (bank) RA question: totals, where students go wrong, each question, each student."""
    students = _students(db, class_group)
    questions = (db.query(RAQuestion.id, RAQuestion.title, RAQuestion.is_published)
                 .filter(RAQuestion.is_deleted == 0, RAQuestion.owner_assessment_id.is_(None))
                 .order_by(RAQuestion.id).all())
    question_ids = [q.id for q in questions]
    parts = _parts(db, question_ids)
    parts_of: Dict[int, List[int]] = defaultdict(list)
    for p in parts:
        parts_of[p.question_id].append(p.id)
    live_parts = {p.id for p in parts}
    attempts = [a for a in _attempts(db, question_ids, list(students)) if a.part_id in live_parts]

    by_user_part: Dict[Tuple[int, int], List[_Attempt]] = defaultdict(list)
    for a in attempts:
        by_user_part[(a.user_id, a.part_id)].append(a)
    solved_pairs = {key for key, rows in by_user_part.items() if any(r.correct for r in rows)}

    question_rows = []
    for q in questions:
        q_attempts = [a for a in attempts if a.question_id == q.id]
        tried = {a.user_id for a in q_attempts}
        solved_all = {u for u in tried if all((u, pid) in solved_pairs for pid in parts_of[q.id])}
        question_rows.append({
            "question_id": q.id, "title": q.title, "is_published": bool(q.is_published),
            "parts": len(parts_of[q.id]), "attempts": len(q_attempts), "students": len(tried),
            "students_solved": len(solved_all),
            "completion_rate": len(solved_all) / len(tried) if tried else None,
            "verdicts": _verdicts(q_attempts),
        })

    per_user: Dict[int, dict] = {}
    for a in attempts:
        s = per_user.setdefault(a.user_id, {"submissions": 0, "questions": set(), "parts": set(),
                                            "first": a.created_at, "last": a.created_at})
        s["submissions"] += 1
        s["questions"].add(a.question_id)
        s["parts"].add(a.part_id)
        s["last"] = a.created_at
    student_rows = []
    completions = []
    for uid, s in sorted(per_user.items()):
        solved = sum(1 for pid in s["parts"] if (uid, pid) in solved_pairs)
        percent = round(solved / len(s["parts"]) * 100) if s["parts"] else None
        if percent is not None:
            completions.append(percent)
        student_rows.append({
            "user_id": uid, **students[uid], "submissions": s["submissions"],
            "questions_tried": len(s["questions"]), "parts_tried": len(s["parts"]), "parts_solved": solved,
            "completion_percent": percent, "first_activity_at": _iso(s["first"]), "last_activity_at": _iso(s["last"]),
        })

    return {
        "totals": {
            "submissions": len(attempts),
            "students_engaged": len(per_user),
            "registered_students": len(students),
            "avg_completion_percent": round(sum(completions) / len(completions)) if completions else None,
            "questions": len(questions),
        },
        "verdicts": _verdicts(attempts),
        "top_errors": _top_errors(attempts),
        "questions": question_rows,
        "students": student_rows,
    }


# ── one question ─────────────────────────────────────────────────────────────
def question_analytics(db: Session, question_id: int, class_group: Optional[str] = None) -> Optional[dict]:
    """Per part: who tried, who solved, how many submits it took, which mistakes. Per student: each part.

    Works for an assessment's own copy of a question too (that is what its students attempted)."""
    q = db.query(RAQuestion).filter(RAQuestion.id == question_id).first()
    if q is None:
        return None
    students = _students(db, class_group)
    parts = _parts(db, [q.id])
    attempts = [a for a in _attempts(db, [q.id], list(students)) if a.part_id in {p.id for p in parts}]
    by_user_part: Dict[Tuple[int, int], List[_Attempt]] = defaultdict(list)
    for a in attempts:
        by_user_part[(a.user_id, a.part_id)].append(a)

    part_rows = []
    for i, p in enumerate(parts):
        p_attempts = [a for a in attempts if a.part_id == p.id]
        users = {a.user_id for a in p_attempts}
        to_correct = [n for n in (_submits_to_correct(by_user_part[(u, p.id)]) for u in users) if n is not None]
        part_rows.append({
            "part_id": p.id, "label": _part_label(p, i, len(parts)), "marks": p.marks or 0,
            "students": len(users), "students_solved": len(to_correct), "attempts": len(p_attempts),
            "avg_submits_to_correct": _mean(to_correct),
            "verdicts": _verdicts(p_attempts), "top_errors": _top_errors(p_attempts),
        })

    total_marks = sum(p.marks or 0 for p in parts)
    student_rows = []
    for uid in sorted({a.user_id for a in attempts}, key=lambda u: students[u]["email"]):
        cells, earned, last = [], 0, None
        for p in parts:
            rows = by_user_part.get((uid, p.id), [])
            solved = any(r.correct for r in rows)
            earned += (p.marks or 0) if solved else 0
            if rows:
                last = max(last, rows[-1].created_at) if last else rows[-1].created_at
            cells.append({"part_id": p.id, "attempts": len(rows), "solved": solved,
                          "submits_to_correct": _submits_to_correct(rows),
                          "last_verdict": rows[-1].verdict if rows else None})
        student_rows.append({
            "user_id": uid, **students[uid], "attempts": sum(c["attempts"] for c in cells),
            "parts_solved": sum(1 for c in cells if c["solved"]), "marks_earned": earned, "marks_total": total_marks,
            "parts": cells, "last_attempt_at": _iso(last),
        })

    return {
        "question_id": q.id, "title": q.title, "is_assessment_copy": q.owner_assessment_id is not None,
        "student_count": len(student_rows),
        "solved_count": sum(1 for s in student_rows if s["parts_solved"] == len(parts) and parts),
        "verdicts": _verdicts(attempts), "top_errors": _top_errors(attempts),
        "parts": part_rows, "students": student_rows,
    }


def student_attempts(db: Session, question_id: int, student_id: int) -> dict:
    """Every attempt one student made at a question, oldest first, as the grader saw it."""
    parts = _parts(db, [question_id])
    labels = {p.id: _part_label(p, i, len(parts)) for i, p in enumerate(parts)}
    rows = (db.query(RAAttempt).filter(RAAttempt.question_id == question_id, RAAttempt.user_id == student_id)
            .order_by(RAAttempt.created_at.asc(), RAAttempt.id.asc()).all())
    out = []
    for a in rows:
        try:
            result = json.loads(a.result_json) if a.result_json else {}
        except (TypeError, ValueError):
            result = {}
        out.append({
            "id": a.id, "part_id": a.part_id, "part_label": labels.get(a.part_id, ""),
            "created_at": _iso(a.created_at), "answer": a.answer, "verdict": a.verdict,
            "correct": bool(a.override_is_correct if a.override_is_correct is not None else a.is_correct),
            "overridden": a.override_is_correct is not None, "method": a.method,
            "message": result.get("message") or "", "error": result.get("error"),
        })
    user = db.query(User.email, User.name).filter(User.id == student_id).first()
    return {"student_id": student_id, "email": user.email if user else "", "name": user.name if user else None,
            "attempts": out}
