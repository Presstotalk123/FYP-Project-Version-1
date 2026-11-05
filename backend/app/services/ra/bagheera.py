"""Bagheera, the platform's AI tutor, on RA questions: hints only, never grades.

Where it appears (practice questions only, as on SQL questions: never in an assessment
and never on a question that hides correctness):
  * **chat**: the student asks anything about the question; and
  * **Explain my mistake**: after a wrong Submit, one explanation per attempt in words of
    what the grader found (saved, so asking again doesn't call the AI again).
Both share one conversation per student and question, and staff can read it in analytics.

What Bagheera is told: the question, its parts, the schema, the data shown with the
question, the student's current answer (or boxes, for a multi-step part), and their last
Submit on the part **as the student saw it** (verdict, counterexample, the ✓/◐/○ step
feedback if the question shows it, and a multi-step part's marks per step). It is never
given the model answer. Every reply then goes through the leak guard (bagheera_guard.py):
if it contains an expression that solves a part or one of its model steps, it is
regenerated once with a warning, and if that leaks too it is replaced by a fixed hint.
"""
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.ra.answer_format import FINAL_ANSWER, MIXED, MULTI_STEP
from app.models.ra_attempt import RAAttempt
from app.models.ra_bagheera_message import RABagheeraMessage
from app.models.ra_question import RAQuestion
from app.models.ra_question_part import RAQuestionPart
from app.models.user import User
from app.services.ra import bagheera_guard, bagheera_llm, multi_step, questions as svc

MEMORY_MESSAGES = 10
MAX_ROWS_SHOWN = 12
SAFE_REPLY = ("I started to write an expression that would give the answer away, so I've held it back. "
              "Let's go one idea at a time instead: tell me which part of the question you're unsure about "
              "(which relations you need, how to combine them, or how to express \"all\" or \"none\"), "
              "and I'll give you a hint for that step.")

RULES = """You are Bagheera, a friendly tutor helping a university student with a relational algebra (RA) \
question on the Akela learning platform. The course uses the notation of its lecture slides:
σ condition (R), Π attributes (R), ρ NewName(a, b) (R), R ⋈ S, R ⋈ condition S, R × S, R ∪ S, R ∩ S, R − S,
R ÷ S, δ (R), γ groups, AGG(attr) → name (R), outer joins ⟕ ⟖ ⟗, and steps written as R1 := expression.
σ, Π and ρ apply to the relation right after them; brackets apply them to more. Set operators need the
same attributes on both sides. In this course a stored table never contains NULLs.

Your rules:
- NEVER write the answer to this question, to any of its parts, or to any step of it, in RA or in words that
  spell it out operator by operator. The platform checks your replies and hides any that do.
- Give hints: ask a guiding question, name the idea or the operator that fits, point at the line of the
  student's answer that goes wrong and say why, or explain what the grader's counterexample shows.
- You may show tiny RA examples on made-up relations (e.g. R(A, B), S(B, C)), never on this question's tables.
- You do not grade. If asked whether an answer is correct, tell the student to Submit: the grader decides
  (it proves answers equivalent on every valid database, or shows a database where they differ).
- Be concise: a few sentences, or a short list. Write RA in backticks."""

EXPLAIN = """The student pressed "Explain my mistake" after the Submit shown below was marked wrong. In a few \
sentences, explain what the grader's result shows about their answer: use the counterexample (the small \
database, the result the question expects and the result their answer gives) to say which tuples are missing \
or extra and which part of their answer causes that. Then give ONE hint about what to change, without \
writing the corrected answer."""


def available(q: RAQuestion, user: User) -> Optional[str]:
    """None if Bagheera may help on this question, else why not."""
    if not bagheera_llm.configured():
        return "Bagheera isn't set up on this server."
    if svc.is_staff(user):
        return None
    if q.owner_assessment_id is not None:
        return "Bagheera is off in assessments."
    if q.hide_correctness:
        return "Bagheera is off for this question."
    return None


def _require(q: RAQuestion, user: User) -> None:
    reason = available(q, user)
    if reason:
        raise HTTPException(status.HTTP_403_FORBIDDEN, reason)


# ── what Bagheera is told ────────────────────────────────────────────────────
def _table(columns: Sequence[str], rows: Sequence[Sequence]) -> str:
    shown = [" | ".join("" if v is None else str(v) for v in r) for r in list(rows)[:MAX_ROWS_SHOWN]]
    more = f"\n  … {len(rows) - MAX_ROWS_SHOWN} more" if len(rows) > MAX_ROWS_SHOWN else ""
    return "  " + " | ".join(columns) + ("\n  " + "\n  ".join(shown) if shown else "\n  (no tuples)") + more


def _case(case: Optional[dict]) -> str:
    if not case:
        return ""
    lines = ["Counterexample database the grader found:"]
    for name, t in (case.get("tables") or {}).items():
        lines.append(f" {name}:\n{_table(t['columns'], t['rows'])}")
    if not case.get("tables"):
        lines.append(" (every relation empty)")
    exp, stu = case.get("expected") or {}, case.get("student") or {}
    if exp:
        lines.append(f" The question expects:\n{_table(exp['columns'], exp['rows'])}")
    if stu:
        lines.append(f" The student's answer gives:\n{_table(stu['columns'], stu['rows'])}")
    return "\n".join(lines)


def _last_submit(q: RAQuestion, part: RAQuestionPart, attempt: Optional[RAAttempt]) -> str:
    if attempt is None:
        return "The student hasn't submitted this part yet."
    try:
        result = json.loads(attempt.result_json or "{}")
    except ValueError:
        result = {}
    lines = [f"Their last Submit on this part:\n{attempt.answer}",
             f"Grader's verdict: {result.get('verdict', attempt.verdict)} — {result.get('message', '')}"]
    err = result.get("error")
    if err:
        lines.append(f"Error at line {err.get('line')}: {err.get('message')} {err.get('hint') or ''}".strip())
    if result.get("extra_rows"):
        lines.append(f"Tuples it has that it shouldn't (on the question's data): {result['extra_rows'][:10]}")
    lines.append(_case(result.get("counterexample")))
    marking = result.get("marking")
    if marking:
        lines.append(f"Marks: {marking.get('earned')} of {marking.get('total')}")
        for s in marking.get("steps", []):
            lines.append(f" step {s.get('name') or 'final'} ({s.get('prompt')}): {s.get('earned')} of "
                         f"{s.get('marks')} marks, {s.get('status')}")
    elif q.show_step_direction and (q.answer_format or MIXED) != FINAL_ANSWER and result.get("steps"):
        lines.append("Step feedback (✓ matches a step of the model solution, ◐ same kind of step but different "
                     "tuples, ○ no matching step — fine for a different method):")
        sym = {"match": "✓", "close": "◐", "none": "○"}
        for s in result["steps"]:
            lines.append(f" {sym.get(s.get('status'), '○')} {s.get('name') or 'final'}: {s.get('text')}")
    return "\n".join(x for x in lines if x)


def context(db: Session, q: RAQuestion, part: RAQuestionPart, user: User, current: Optional[str],
            boxes: Optional[Sequence[str]], attempt: Optional[RAAttempt] = None) -> str:
    parts = svc.parts_of(db, q)
    fmt = q.answer_format or MIXED
    out = [f"QUESTION: {q.title}", q.description or ""]
    if len(parts) > 1:
        label = part.label or str([p.id for p in parts].index(part.id) + 1)
        out.append(f"The student is on part {label} ({part.marks} marks): {part.description or ''}")
    out.append(f"Schema (SQL):\n{q.schema_sql}")
    shown, source = svc.shown_database(q)
    if shown is not None:
        out.append("Data shown with the question" + (" (made-up example data)" if source == "example" else "") + ":")
        for t in shown.tables:
            out.append(f" {t.name}:\n{_table(t.column_names, t.rows)}")
    steps = multi_step.steps_of(part) if fmt == MULTI_STEP else []
    if steps:
        out.append("This part is answered in steps, one box each (a later box may use an earlier one by name):")
        for k, s in enumerate(steps):
            out.append(f" {s.name or 'final'} ({s.marks} marks): {s.prompt}")
        if boxes is not None:
            out.append("The student's boxes right now:")
            for k, s in enumerate(steps):
                text = (list(boxes) + [""] * len(steps))[k].strip() or "(empty)"
                out.append(f" {s.name or 'final'} := {text}" if s.name else f" final: {text}")
    else:
        if fmt == FINAL_ANSWER:
            out.append("This question asks for one expression, without steps (no R1 := …).")
        out.append(f"The student's answer right now:\n{(current or '').strip() or '(empty)'}")
    if attempt is None:
        attempt = (db.query(RAAttempt).filter(RAAttempt.user_id == user.id, RAAttempt.question_id == q.id,
                                              RAAttempt.part_id == part.id)
                   .order_by(RAAttempt.created_at.desc(), RAAttempt.id.desc()).first())
    out.append(_last_submit(q, part, attempt))
    return "\n\n".join(x for x in out if x)


# ── replies ───────────────────────────────────────────────────────────────────
@dataclass
class Reply:
    content: str
    guarded: bool
    blocked: Optional[str]


async def _guarded_reply(db: Session, q: RAQuestion, system: str, messages: List[Dict[str, str]]) -> Reply:
    prepared = [svc.prepared_for(q, p) for p in svc.parts_of(db, q)]
    first = await bagheera_llm.complete(system, messages)
    if not bagheera_guard.leaks(first, prepared):
        return Reply(first, False, None)
    retry = messages + [{"role": "assistant", "content": first},
                        {"role": "user", "content": "(Platform check: that reply contained an expression that "
                                                    "solves the question or one of its steps, so the student won't "
                                                    "see it. Reply again with hints only, without that expression.)"}]
    second = await bagheera_llm.complete(system, retry)
    if not bagheera_guard.leaks(second, prepared):
        return Reply(second, True, first)
    return Reply(SAFE_REPLY, True, first + "\n\n---\n\n" + second)


def _history(db: Session, user: User, q: RAQuestion) -> List[RABagheeraMessage]:
    rows = (db.query(RABagheeraMessage).filter(RABagheeraMessage.user_id == user.id,
                                               RABagheeraMessage.question_id == q.id)
            .order_by(RABagheeraMessage.created_at.desc(), RABagheeraMessage.id.desc())
            .limit(MEMORY_MESSAGES).all())
    return list(reversed(rows))


def _save(db: Session, **fields) -> RABagheeraMessage:
    m = RABagheeraMessage(**fields)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


async def chat(db: Session, user: User, q: RAQuestion, part: RAQuestionPart, message: str,
               current: Optional[str], boxes: Optional[Sequence[str]]) -> RABagheeraMessage:
    _require(q, user)
    system = RULES + "\n\n" + context(db, q, part, user, current, boxes)
    memory = [{"role": m.role, "content": m.content} for m in _history(db, user, q)]
    reply = await _call(db, q, system, memory + [{"role": "user", "content": message}])
    _save(db, user_id=user.id, question_id=q.id, part_id=part.id, kind="chat", role="user", content=message)
    return _save(db, user_id=user.id, question_id=q.id, part_id=part.id, kind="chat", role="assistant",
                 content=reply.content, guarded=int(reply.guarded), blocked_content=reply.blocked)


async def explain(db: Session, user: User, q: RAQuestion, attempt_id: int) -> RABagheeraMessage:
    """One explanation per wrong attempt; asking again returns the saved one."""
    _require(q, user)
    attempt = db.query(RAAttempt).filter(RAAttempt.id == attempt_id, RAAttempt.question_id == q.id,
                                         RAAttempt.user_id == user.id).first()
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Attempt not found")
    saved = db.query(RABagheeraMessage).filter(RABagheeraMessage.attempt_id == attempt.id,
                                               RABagheeraMessage.kind == "explain").first()
    if saved is not None:
        return saved
    part = db.query(RAQuestionPart).filter(RAQuestionPart.id == attempt.part_id).first()
    if part is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Part not found")
    full_marks = attempt.marks_earned is not None and attempt.marks_earned >= (part.marks or 0)
    if attempt.is_correct or full_marks:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This attempt is correct: nothing to explain.")
    boxes = json.loads(attempt.step_answers_json) if attempt.step_answers_json else None
    system = RULES + "\n\n" + context(db, q, part, user, attempt.answer, boxes, attempt)
    reply = await _call(db, q, system, [{"role": "user", "content": EXPLAIN}])
    return _save(db, user_id=user.id, question_id=q.id, part_id=part.id, kind="explain", role="assistant",
                 content=reply.content, attempt_id=attempt.id, guarded=int(reply.guarded),
                 blocked_content=reply.blocked)


async def _call(db: Session, q: RAQuestion, system: str, messages: List[Dict[str, str]]) -> Reply:
    try:
        return await _guarded_reply(db, q, system, messages)
    except bagheera_llm.TutorUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e))


# ── reading conversations ────────────────────────────────────────────────────
def message_out(m: RABagheeraMessage, staff: bool = False) -> dict:
    out = {"id": m.id, "part_id": m.part_id, "kind": m.kind, "role": m.role, "content": m.content,
           "attempt_id": m.attempt_id, "guarded": bool(m.guarded),
           "created_at": m.created_at.isoformat() if m.created_at else None}
    if staff:
        out["blocked_content"] = m.blocked_content
    return out


def conversation(db: Session, user_id: int, question_id: int, staff: bool = False) -> List[dict]:
    rows = (db.query(RABagheeraMessage).filter(RABagheeraMessage.user_id == user_id,
                                               RABagheeraMessage.question_id == question_id)
            .order_by(RABagheeraMessage.created_at.asc(), RABagheeraMessage.id.asc()).all())
    return [message_out(m, staff) for m in rows]
