"""On-demand analytics over er_submissions. No rollup tables, no caching:
class sizes are tens of students, staff want fresh numbers."""
import json
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session, load_only

from app.models.assessment_item import AssessmentItem
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.er_submission import ErSubmission
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.erd_tutor_message import ErdTutorMessage
from app.models.user import User

VALID_CONTEXTS = {"practice", "assessment", "all"}

# Keyword topic buckets for "what do students ask Baloo about". Deterministic on
# purpose: free at any volume and stable across reloads. Order matters — the
# first bucket whose keyword matches wins, so the more specific topics (weak
# entities before entities/keys) come first.
QUERY_TOPICS: list[tuple[str, tuple[str, ...]]] = [
    ("weak entities", ("weak entit", "partial key", "discriminator", "identifying relationship")),
    ("cardinality & participation", ("cardinal", "particip", "many-to-many", "many to many",
                                     "one-to-many", "one to many", "one-to-one", "one to one",
                                     "1:n", "m:n", "n:m", "1:1")),
    ("keys & identifiers", ("key", "identifier", "underline")),
    ("attributes", ("attribute", "composite", "multivalued", "multi-valued", "derived")),
    ("notation & style", ("notation", "chen", "diamond", "rectangle", "oval", "double line", "symbol")),
    ("using the editor", ("draw.io", "drawio", "canvas", "export", "upload", "zoom", "undo", "file")),
    ("relationships", ("relationship", "connect", "associat", "ternary", "recursive")),
    ("entities", ("entity", "entities",)),
]

OTHER_TOPIC = "other"


def classify_query_topic(text: str) -> str:
    """Bucket one student question into a topic; 'other' when nothing matches."""
    lowered = (text or "").lower()
    for topic, keywords in QUERY_TOPICS:
        if any(k in lowered for k in keywords):
            return topic
    return OTHER_TOPIC


def _j(value, default):
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return default
    return parsed if isinstance(parsed, type(default)) else default


def _context_filter(query, context: str):
    if context == "practice":
        return query.filter(ERDiagramQuestion.owner_assessment_id.is_(None))
    if context == "assessment":
        return query.filter(ERDiagramQuestion.owner_assessment_id.isnot(None))
    return query


def question_family(db: Session, question_id: int) -> list[int]:
    """A bank question and every assessment clone taken from it (or vice versa).

    Publishing an assessment deep-copies its questions, so a student's assessment
    attempt is recorded against the clone, not the question staff see in Problems.
    Without this the master's analytics read as empty however many assessments used
    it, and the clone's data is only reachable by knowing an id nothing links to.

    The link lives on the assessment item, which keeps the original id in
    source_item_id when it repoints item_id at the clone. Accepts either end: given
    a clone, the master is resolved first so siblings come along too.
    """
    master_id = (
        db.query(AssessmentItem.source_item_id)
        .filter(AssessmentItem.item_type == "er_question",
                AssessmentItem.item_id == question_id,
                AssessmentItem.source_item_id.isnot(None))
        .scalar()
    ) or question_id

    clone_ids = [
        row[0]
        for row in db.query(AssessmentItem.item_id)
        .filter(AssessmentItem.item_type == "er_question",
                AssessmentItem.source_item_id == master_id)
        .all()
    ]
    # Deduped and ordered so the cache key below is stable across calls.
    return sorted({master_id, question_id, *clone_ids})


def _submissions(
    db: Session,
    context: str,
    question_id: Optional[int] = None,
    class_group: Optional[str] = None,
    student_id: Optional[int] = None,
    question_ids: Optional[list[int]] = None,
):
    q = (
        db.query(ErSubmission)
        # Aggregates never need the heavy artifact columns (submitted_xml can be
        # 500KB per row); those stay exclusive to the single-attempt endpoint.
        .options(load_only(
            ErSubmission.id,
            ErSubmission.user_id,
            ErSubmission.er_diagram_question_id,
            ErSubmission.score_percent,
            ErSubmission.score_label,
            ErSubmission.checks_json,
            ErSubmission.submitted_image_storage_key,
            ErSubmission.hint_level_at_submit,
            ErSubmission.ibl_stage_at_submit,
            ErSubmission.created_at,
        ))
        .join(ERDiagramQuestion,
              ERDiagramQuestion.id == ErSubmission.er_diagram_question_id)
        .filter(ERDiagramQuestion.is_deleted == 0)
    )
    q = _context_filter(q, context)
    if question_ids is not None:
        q = q.filter(ErSubmission.er_diagram_question_id.in_(question_ids))
    elif question_id is not None:
        q = q.filter(ErSubmission.er_diagram_question_id == question_id)
    if student_id is not None:
        q = q.filter(ErSubmission.user_id == student_id)
    if class_group is not None:
        q = q.join(User, User.id == ErSubmission.user_id).filter(
            User.class_group == class_group
        )
    return q.order_by(ErSubmission.created_at.asc(), ErSubmission.id.asc()).all()


def list_class_groups(db: Session) -> list:
    """Distinct class groups carried by users, for the analytics filter dropdown."""
    rows = (
        db.query(User.class_group)
        .filter(User.class_group.isnot(None), User.class_group != "")
        .distinct()
        .order_by(User.class_group.asc())
        .all()
    )
    return [r[0] for r in rows]


# Topic tallies scan at most this many of the newest chat messages: proportions
# barely move beyond a few thousand samples, and the bound keeps overview latency
# flat as semesters of history accumulate.
QUERY_SCAN_LIMIT = 5000


def _student_queries(
    db: Session,
    context: str,
    class_group: Optional[str] = None,
    question_id: Optional[int] = None,
    student_id: Optional[int] = None,
    question_ids: Optional[list[int]] = None,
):
    """Student chat questions to Baloo (newest first), honoring the filters."""
    q = (
        db.query(ErdTutorMessage)
        .join(ErdTutorConversation,
              ErdTutorConversation.id == ErdTutorMessage.conversation_id)
        .join(ERDiagramQuestion,
              ERDiagramQuestion.id == ErdTutorConversation.er_diagram_question_id)
        .filter(ErdTutorMessage.role == "user",
                ErdTutorMessage.mode == "query",
                ERDiagramQuestion.is_deleted == 0)
    )
    q = _context_filter(q, context)
    if question_ids is not None:
        q = q.filter(ErdTutorConversation.er_diagram_question_id.in_(question_ids))
    elif question_id is not None:
        q = q.filter(ErdTutorConversation.er_diagram_question_id == question_id)
    if student_id is not None:
        q = q.filter(ErdTutorConversation.user_id == student_id)
    if class_group is not None:
        q = q.join(User, User.id == ErdTutorConversation.user_id).filter(
            User.class_group == class_group
        )
    return (
        q.order_by(ErdTutorMessage.created_at.desc(), ErdTutorMessage.id.desc())
        .limit(QUERY_SCAN_LIMIT)
        .all()
    )


def query_topics(
    db: Session,
    context: str,
    class_group: Optional[str] = None,
    examples_per_topic: int = 5,
    question_ids: Optional[list[int]] = None,
) -> list:
    """Tally of what students ask Baloo about, bucketed by keyword topic, with
    the most recent real questions kept as examples.

    Cohort-wide by default; pass `question_ids` for one question's own tally —
    what students got stuck on *here*, which is what makes it actionable when
    the answer is to reword the problem statement.
    """
    tally: dict[str, dict] = {}
    for msg in _student_queries(db, context, class_group, question_ids=question_ids):
        text = (msg.content or "").strip()
        if not text:
            continue
        topic = classify_query_topic(text)
        slot = tally.setdefault(topic, {"topic": topic, "count": 0, "examples": []})
        slot["count"] += 1
        if len(slot["examples"]) < examples_per_topic:
            slot["examples"].append(text)
    return sorted(tally.values(), key=lambda t: -t["count"])


def _check_rates(rows) -> dict:
    """Per-check status tallies across submissions. Unknown statuses count as
    fail (mirrors scoring normalization); not_applicable is excluded."""
    tallies: dict[str, dict] = defaultdict(
        lambda: {"pass": 0, "partial": 0, "fail": 0, "total": 0, "dimension": None}
    )
    for row in rows:
        for check in _j(row.checks_json, []):
            cid = str(check.get("id") or "")
            status = str(check.get("status") or "").strip().lower()
            if not cid or status == "not_applicable":
                continue
            slot = tallies[cid]
            slot["dimension"] = check.get("dimension") or slot["dimension"]
            slot[status if status in ("pass", "partial") else "fail"] += 1
            slot["total"] += 1
    return tallies


def _rubric_criteria(question: ERDiagramQuestion) -> dict:
    rubric = _j(question.rubric_json, {})
    out = {}
    for check in rubric.get("checks", []) if isinstance(rubric, dict) else []:
        if isinstance(check, dict) and check.get("id"):
            out[str(check["id"])] = {
                "pass_criteria": check.get("pass_criteria") or "",
                "requirement_level": check.get("requirement_level") or "",
                "dimension": check.get("dimension") or "",
            }
    return out


def question_analytics(
    db: Session,
    question_id: int,
    context: str,
    class_group: Optional[str] = None,
) -> Optional[dict]:
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id,
                ERDiagramQuestion.is_deleted == 0)
        .first()
    )
    if question is None:
        return None

    # The whole family, so a bank question shows the assessment attempts taken
    # against its clones. `context` then does the splitting it always did: the
    # master carries the practice rows, its clones the assessment ones.
    family = question_family(db, question_id)
    rows = _submissions(db, context, class_group=class_group, question_ids=family)
    percents = [r.score_percent for r in rows if r.score_percent is not None]

    histogram = [{"bucket": b, "count": 0} for b in range(0, 100, 10)]
    for p in percents:
        histogram[min(int(p // 10), 9)]["count"] += 1

    criteria = _rubric_criteria(question)
    checks = []
    for cid, t in sorted(_check_rates(rows).items()):
        meta = criteria.get(cid, {})
        total = t["total"] or 1
        checks.append({
            "id": cid,
            "dimension": t["dimension"] or meta.get("dimension") or "",
            "requirement_level": meta.get("requirement_level", ""),
            "pass_criteria": meta.get("pass_criteria", ""),
            "pass_rate": t["pass"] / total,
            "partial_rate": t["partial"] / total,
            "fail_rate": t["fail"] / total,
            "total": t["total"],
        })

    per_student: dict[int, dict] = {}
    for r in rows:
        s = per_student.setdefault(r.user_id, {
            "user_id": r.user_id, "attempts": 0,
            "best_percent": None, "latest_percent": None, "last_attempt_at": None,
        })
        s["attempts"] += 1
        if r.score_percent is not None:
            s["latest_percent"] = r.score_percent
            if s["best_percent"] is None or r.score_percent > s["best_percent"]:
                s["best_percent"] = r.score_percent
        s["last_attempt_at"] = r.created_at.isoformat() if r.created_at else None
    user_meta = {
        uid: {"email": email, "class_group": group}
        for uid, email, group in (
            db.query(User.id, User.email, User.class_group)
            .filter(User.id.in_(per_student.keys()))
            .all()
        )
    } if per_student else {}
    students = [
        {
            **s,
            "email": user_meta.get(uid, {}).get("email", ""),
            "class_group": user_meta.get(uid, {}).get("class_group"),
        }
        for uid, s in sorted(per_student.items())
    ]

    return {
        "question_id": question.id,
        "title": question.title,
        "attempt_count": len(rows),
        "student_count": len(per_student),
        "avg_percent": round(sum(percents) / len(percents), 1) if percents else None,
        "histogram": histogram,
        "checks": checks,
        "students": students,
        # What students asked Baloo while working on THIS question — the same
        # tally the class overview shows, narrowed to the family so an assessment
        # clone's chat counts toward the question it was cloned from.
        "query_topics": query_topics(db, context, class_group, question_ids=family),
    }


def student_submissions(db: Session, question_id: int, student_id: int) -> dict:
    # Same family as question_analytics, so a student listed there by an assessment
    # attempt still has a journey to drill into from the master's page.
    rows = _submissions(db, "all", student_id=student_id,
                        question_ids=question_family(db, question_id))
    attempts = [{
        "id": r.id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "percent": r.score_percent,
        "label": r.score_label,
        "hint_level_at_submit": r.hint_level_at_submit,
        "ibl_stage_at_submit": r.ibl_stage_at_submit,
        "has_image": bool(r.submitted_image_storage_key),
    } for r in rows]

    conv = (
        db.query(ErdTutorConversation)
        .filter(ErdTutorConversation.user_id == student_id,
                ErdTutorConversation.er_diagram_question_id == question_id)
        .first()
    )
    queries_asked = 0
    topics: list = []
    if conv is not None:
        messages = (
            db.query(ErdTutorMessage)
            .filter(ErdTutorMessage.conversation_id == conv.id,
                    ErdTutorMessage.role == "user",
                    ErdTutorMessage.mode == "query")
            .all()
        )
        queries_asked = len(messages)
        seen = set()
        for m in messages:
            topic = classify_query_topic(m.content or "")
            if topic not in seen:
                seen.add(topic)
                topics.append(topic)

    return {
        "student_id": student_id,
        "attempts": attempts,
        "chat": {"queries_asked": queries_asked, "topics": topics},
    }


def class_overview(
    db: Session, context: str, class_group: Optional[str] = None
) -> dict:
    rows = _submissions(db, context, class_group=class_group)

    by_question: dict[int, list] = defaultdict(list)
    for r in rows:
        by_question[r.er_diagram_question_id].append(r)
    q_meta = dict(
        db.query(ERDiagramQuestion.id, ERDiagramQuestion.title)
        .filter(ERDiagramQuestion.id.in_(by_question.keys())).all()
    ) if by_question else {}

    # One checks_json parse per question; the dimension totals fold the same
    # per-question tallies rather than re-parsing every row a second time.
    dim: dict[str, dict] = defaultdict(lambda: {"fail": 0, "partial": 0, "total": 0})
    questions = []
    top_failing = []
    for qid, q_rows in sorted(by_question.items()):
        percents = [r.score_percent for r in q_rows if r.score_percent is not None]
        questions.append({
            "question_id": qid,
            "title": q_meta.get(qid, ""),
            "attempts": len(q_rows),
            "students": len({r.user_id for r in q_rows}),
            "avg_percent": round(sum(percents) / len(percents), 1) if percents else None,
        })
        for cid, t in _check_rates(q_rows).items():
            d = dim[t["dimension"] or "other"]
            d["fail"] += t["fail"]
            d["partial"] += t["partial"]
            d["total"] += t["total"]
            if t["total"]:
                top_failing.append({
                    "question_id": qid,
                    "question_title": q_meta.get(qid, ""),
                    "check_id": cid,
                    "dimension": t["dimension"] or "",
                    "fail_rate": t["fail"] / t["total"],
                    "attempts": t["total"],
                })
    top_failing.sort(key=lambda c: c["fail_rate"], reverse=True)

    dimensions = [{
        "dimension": name,
        "fail_rate": d["fail"] / d["total"] if d["total"] else 0.0,
        "partial_rate": d["partial"] / d["total"] if d["total"] else 0.0,
        "checks_evaluated": d["total"],
    } for name, d in sorted(dim.items())]

    return {
        "dimensions": dimensions,
        "top_failing_checks": top_failing[:10],
        "query_topics": query_topics(db, context, class_group),
        "questions": questions,
    }
