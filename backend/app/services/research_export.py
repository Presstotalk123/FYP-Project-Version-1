"""Research/LAD data export: cohort-level aggregates and a per-student anonymized CSV.

Two staff-only deliverables, both computed live here (no rollup tables):
- ``compute_summary`` — the JSON aggregate behind ``GET /admin/export/summary``,
  wrapped in the RESEARCH_EXPORT cache namespace (date-stamped key) at the endpoint.
- ``stream_raw_csv_rows`` — the streamed per-student CSV behind ``GET /admin/export/raw-csv``.

Every query that defines the student population goes through ``_student_ids``, which
applies ``assessment_registration.exclude_test_groups`` so staff/test class groups
(settings.ANALYTICS_EXCLUDED_CLASS_GROUPS) never appear in research data. Functions take
``db: Session`` and return plain dict/list/Pydantic values — never ORM objects — so the
summary is fully serialized before the cache_read session boundary closes.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import csv
import json
import re
from collections import defaultdict

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.attempt import Attempt
from app.models.lab_attempt import LabAttempt
from app.models.lab_session import LabSession
from app.models.lab_task_submission import LabTaskSubmission
from app.models.learning_event import LearningEvent
from app.models.question_concept import QuestionConcept
from app.models.solo_classification import SoloClassification
from app.models.sql_tutor_conversation import SqlTutorConversation
from app.models.tutor_chat_conversation import TutorChatConversation
from app.models.tutor_chat_message import TutorChatMessage
from app.models.user import User, UserRole
from app.services import assessment_registration
from app.services.learning_telemetry import (
    EVENT_HINT_REQUESTED,
    EVENT_SCAFFOLDING_CHANGED,
)
from app.services.scaffolding_engine import DEFAULT_LEVEL, LEVELS
from app.services.solo_classifier import SOLO_LEVELS

# Opportunity index cap for the learning-curve buckets — keeps the response bounded when a
# rare student has hundreds of attempts on one concept.
MAX_OPPORTUNITY = 10

# Ordinal mapping for avg_solo_level_numeric (0-indexed, least->most sophisticated).
_SOLO_NUMERIC = {level: i for i, level in enumerate(SOLO_LEVELS)}
_LEVEL_INDEX = {level: i for i, level in enumerate(LEVELS)}


# --- Misconception taxonomy -----------------------------------------------------------
# First-match-wins: most specific / highest-signal patterns first (e.g. an "ambiguous
# column" join error must classify as wrong_join, not unknown_column). This is a first
# pass written against generic SQLite/Postgres phrasing — validate against a real sample
# of this DB's error_message values before relying on it for research conclusions.
_MISCONCEPTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("syntax_error", re.compile(r"\bsyntax error\b|unexpected token|parse error|incomplete input", re.I)),
    ("wrong_join", re.compile(r"\bambiguous column\b|cartesian|\bjoin\b.*\bcondition\b", re.I)),
    ("unknown_column", re.compile(r"\bno such column\b|\bunknown column\b|column .* does not exist", re.I)),
    ("unknown_table", re.compile(r"\bno such table\b|relation .* does not exist|table .* does(n'?t| not) exist", re.I)),
    ("type_mismatch", re.compile(r"\btype mismatch\b|datatype mismatch|cannot compare|invalid input syntax for", re.I)),
    ("aggregate_misuse", re.compile(r"must appear in the group by|aggregate function calls cannot be nested|not a group by expression|misuse of aggregate", re.I)),
    ("constraint_violation", re.compile(r"unique constraint|foreign key constraint|not null constraint|check constraint", re.I)),
    ("permission_or_timeout", re.compile(r"permission denied|\btimeout\b|timed out|too many .* connections", re.I)),
]
_OTHER_CATEGORY = "other_uncategorized"


def _classify_error(message: str) -> str:
    for category, pattern in _MISCONCEPTION_PATTERNS:
        if pattern.search(message):
            return category
    return _OTHER_CATEGORY


# --- Student population ----------------------------------------------------------------

def _student_ids(db: Session) -> list[int]:
    """Distinct student user ids with staff/test class groups excluded."""
    q = db.query(User.id).filter(User.role == UserRole.STUDENT)
    q = assessment_registration.exclude_test_groups(q, User.class_group)
    return [uid for (uid,) in q.all()]


# --- Summary aggregations --------------------------------------------------------------

def _system_scale(db: Session, student_ids: list[int]) -> dict:
    if not student_ids:
        return {"total_distinct_students": 0, "total_lab_sessions": 0, "total_submissions": 0}
    total_lab_sessions = (
        db.query(func.count(LabSession.id))
        .filter(LabSession.user_id.in_(student_ids))
        .scalar()
        or 0
    )
    # "Total submissions" = graded question attempts + graded lab-task submissions.
    # Raw/ungraded LabAttempt query runs are excluded to avoid double-counting exploratory
    # runs against graded work.
    total_submissions = (
        (db.query(func.count(Attempt.id)).filter(Attempt.user_id.in_(student_ids)).scalar() or 0)
        + (db.query(func.count(LabTaskSubmission.id)).filter(LabTaskSubmission.user_id.in_(student_ids)).scalar() or 0)
    )
    return {
        "total_distinct_students": len(student_ids),
        "total_lab_sessions": int(total_lab_sessions),
        "total_submissions": int(total_submissions),
    }


def _adaptive_efficacy(db: Session, student_ids: list[int]) -> dict:
    distribution = {level: 0 for level in LEVELS}
    restoration_count = 0
    if not student_ids:
        return {"scaffolding_level_distribution": distribution, "restoration_event_count": 0}

    rows = (
        db.query(SqlTutorConversation.scaffolding_level, func.count(SqlTutorConversation.id))
        .filter(SqlTutorConversation.user_id.in_(student_ids))
        .group_by(SqlTutorConversation.scaffolding_level)
        .all()
    )
    for level, cnt in rows:
        distribution[level or DEFAULT_LEVEL] = distribution.get(level or DEFAULT_LEVEL, 0) + int(cnt)

    # Restoration = a scaffolding change moving toward MORE support (lower LEVELS index).
    # Derived from the learning_events payload since there is no explicit direction flag.
    payloads = (
        db.query(LearningEvent.payload_json)
        .filter(
            LearningEvent.user_id.in_(student_ids),
            LearningEvent.event_type == EVENT_SCAFFOLDING_CHANGED,
        )
        .all()
    )
    for (payload_json,) in payloads:
        if not payload_json:
            continue
        try:
            payload = json.loads(payload_json)
        except (ValueError, TypeError):
            continue
        frm = payload.get("from_level")
        to = payload.get("to_level")
        if frm in _LEVEL_INDEX and to in _LEVEL_INDEX and _LEVEL_INDEX[to] < _LEVEL_INDEX[frm]:
            restoration_count += 1

    return {"scaffolding_level_distribution": distribution, "restoration_event_count": restoration_count}


def _solo_transition_matrix(db: Session, student_ids: list[int]) -> dict:
    matrix = {frm: {to: 0 for to in SOLO_LEVELS} for frm in SOLO_LEVELS}
    if not student_ids:
        return {"transition_matrix": matrix}

    rows = (
        db.query(
            SoloClassification.user_id,
            SoloClassification.solo_level,
            SoloClassification.created_at,
        )
        .filter(SoloClassification.user_id.in_(student_ids))
        .order_by(
            SoloClassification.user_id,
            SoloClassification.created_at,
            SoloClassification.id,
        )
        .all()
    )
    # Single pass over user-grouped, time-ordered rows: pair each classification with the
    # student's previous one. The user_id-first ordering resets the pairing at each boundary.
    prev_by_user: dict[int, str] = {}
    for uid, level, _ts in rows:
        prev = prev_by_user.get(uid)
        if prev is not None and prev in matrix and level in matrix[prev]:
            matrix[prev][level] += 1
        prev_by_user[uid] = level
    return {"transition_matrix": matrix}


def _ai_performance(db: Session, student_ids: list[int]) -> dict:
    empty = {"fallback_rate": None, "graceful_degradation_rate": None, "total_classifications": 0}
    if not student_ids:
        return empty
    total = (
        db.query(func.count(SoloClassification.id))
        .filter(SoloClassification.user_id.in_(student_ids))
        .scalar()
        or 0
    )
    if total == 0:
        return empty

    fallback_count = (
        db.query(func.count(SoloClassification.id))
        .filter(
            SoloClassification.user_id.in_(student_ids),
            SoloClassification.used_fallback == 1,
        )
        .scalar()
        or 0
    )
    # Graceful degradation mirrors sql_tutor_adaptive.prepare_turn's used_generic rule:
    # used_fallback OR confidence below threshold.
    degraded_count = (
        db.query(func.count(SoloClassification.id))
        .filter(
            SoloClassification.user_id.in_(student_ids),
            or_(
                SoloClassification.used_fallback == 1,
                SoloClassification.confidence < settings.SOLO_CONFIDENCE_THRESHOLD,
            ),
        )
        .scalar()
        or 0
    )
    return {
        "fallback_rate": round(fallback_count / total, 4),
        "graceful_degradation_rate": round(degraded_count / total, 4),
        "total_classifications": int(total),
    }


def _productive_friction(db: Session, student_ids: list[int]) -> dict:
    if not student_ids:
        return {"by_scaffolding_level": {}}

    # Each (user, question) pair tagged with that pair's CURRENT scaffolding_level (there is
    # no per-attempt historical snapshot). any_correct = did the student ever pass the
    # question; attempts = how many tries that pair took.
    rows = (
        db.query(
            SqlTutorConversation.scaffolding_level,
            Attempt.user_id,
            Attempt.question_id,
            func.count(Attempt.id).label("attempts"),
            func.max(Attempt.is_correct).label("any_correct"),
        )
        .join(
            Attempt,
            (Attempt.user_id == SqlTutorConversation.user_id)
            & (Attempt.question_id == SqlTutorConversation.question_id),
        )
        .filter(SqlTutorConversation.user_id.in_(student_ids))
        .group_by(
            SqlTutorConversation.scaffolding_level,
            Attempt.user_id,
            Attempt.question_id,
        )
        .all()
    )
    buckets: dict[str, dict] = {lvl: {"attempts_sum": 0, "pairs": 0, "passed_pairs": 0} for lvl in LEVELS}
    for level, _uid, _qid, attempts, any_correct in rows:
        lvl = level or DEFAULT_LEVEL
        b = buckets.setdefault(lvl, {"attempts_sum": 0, "pairs": 0, "passed_pairs": 0})
        b["attempts_sum"] += int(attempts)
        b["pairs"] += 1
        b["passed_pairs"] += 1 if any_correct else 0

    return {
        "by_scaffolding_level": {
            lvl: {
                "pass_rate": round(b["passed_pairs"] / b["pairs"], 4) if b["pairs"] else None,
                "avg_attempt_frequency": round(b["attempts_sum"] / b["pairs"], 2) if b["pairs"] else None,
                "sample_size": b["pairs"],
            }
            for lvl, b in buckets.items()
        }
    }


def _learning_curves(db: Session, student_ids: list[int]) -> dict:
    if not student_ids:
        return {"by_concept": {}, "max_opportunity_bucketed": MAX_OPPORTUNITY}

    rows = (
        db.query(
            QuestionConcept.concept_id,
            Attempt.user_id,
            Attempt.submitted_at,
            Attempt.is_correct,
        )
        .join(QuestionConcept, QuestionConcept.question_id == Attempt.question_id)
        .filter(Attempt.user_id.in_(student_ids))
        .order_by(
            QuestionConcept.concept_id,
            Attempt.user_id,
            Attempt.submitted_at,
            Attempt.id,
        )
        .all()
    )
    # Rank each (user, concept)'s attempts 1..N in submission order, then bucket error rate
    # by opportunity index per concept. Uses submission order directly rather than the
    # mutable ConceptMastery.total_attempts snapshot.
    counters: dict[tuple[int, int], int] = defaultdict(int)
    per_concept: dict[int, dict[int, list[int]]] = defaultdict(lambda: defaultdict(list))
    for concept_id, user_id, _ts, is_correct in rows:
        counters[(user_id, concept_id)] += 1
        opp = counters[(user_id, concept_id)]
        if opp <= MAX_OPPORTUNITY:
            per_concept[concept_id][opp].append(0 if is_correct else 1)

    by_concept = {
        str(concept_id): {
            str(opp): round(sum(errs) / len(errs), 4)
            for opp, errs in sorted(buckets.items())
        }
        for concept_id, buckets in per_concept.items()
    }
    return {"by_concept": by_concept, "max_opportunity_bucketed": MAX_OPPORTUNITY}


def _misconception_taxonomy(db: Session, student_ids: list[int]) -> dict:
    counts: dict[str, int] = defaultdict(int)
    if not student_ids:
        return {"category_counts": {}}
    for model in (Attempt, LabAttempt):
        for (msg,) in (
            db.query(model.error_message)
            .filter(
                model.user_id.in_(student_ids),
                model.error_message.isnot(None),
                model.error_message != "",
            )
            .all()
        ):
            counts[_classify_error(msg)] += 1
    return {"category_counts": dict(counts)}


def compute_summary(db: Session) -> dict:
    """Assemble all seven cohort-level aggregates into one fully-serialized dict."""
    student_ids = _student_ids(db)
    return {
        "system_scale": _system_scale(db, student_ids),
        "adaptive_efficacy": _adaptive_efficacy(db, student_ids),
        "solo_articulation": _solo_transition_matrix(db, student_ids),
        "ai_performance": _ai_performance(db, student_ids),
        "productive_friction": _productive_friction(db, student_ids),
        "learning_curves": _learning_curves(db, student_ids),
        "misconception_taxonomy": _misconception_taxonomy(db, student_ids),
    }


# --- Raw CSV export --------------------------------------------------------------------

CSV_COLUMNS = [
    "anon_id",
    "class_group",
    "final_weighted_score",
    "total_time_on_task_min",
    "num_ai_interactions",
    "hint_dependency_ratio",
    "avg_solo_level_numeric",
    "scaffolding_level_at_end",
    "error_category_counts_json",
]


def anon_id(user_id: int) -> str:
    """Stable, non-reversible per-student id: HMAC-SHA256(salt, user_id), 16 hex chars.

    The endpoint refuses to run when RESEARCH_EXPORT_SALT is unset, so this is never
    called with an empty key in practice.
    """
    key = settings.RESEARCH_EXPORT_SALT.encode("utf-8")
    return hmac.new(key, str(user_id).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _prefetch_all_student_metrics(db: Session, student_ids: list[int]) -> dict[int, dict]:
    """One batched (grouped) query per CSV column over the whole student population,
    assembled into {user_id: {metric: value}}. Avoids N+1 while the endpoint streams rows.
    """
    from app.models.assessment_session import AssessmentSession

    metrics: dict[int, dict] = {
        uid: {
            "final_weighted_score": None,
            "total_time_on_task_min": 0.0,
            "num_ai_interactions": 0,
            "hint_count": 0,
            "attempt_count": 0,
            "solo_sum": 0.0,
            "solo_n": 0,
            "scaffolding_level_at_end": None,
            "error_category_counts": defaultdict(int),
        }
        for uid in student_ids
    }
    if not student_ids:
        return metrics

    # final_weighted_score: mean of persisted finalized-session scores (Phase 1 payoff).
    score_rows = (
        db.query(AssessmentSession.user_id, AssessmentSession.weighted_score)
        .filter(
            AssessmentSession.user_id.in_(student_ids),
            AssessmentSession.attempt_complete == 1,
            AssessmentSession.weighted_score.isnot(None),
        )
        .all()
    )
    score_acc: dict[int, list[float]] = defaultdict(list)
    for uid, score in score_rows:
        score_acc[uid].append(score)
    for uid, scores in score_acc.items():
        metrics[uid]["final_weighted_score"] = round(sum(scores) / len(scores), 1)

    # total_time_on_task_min: sum of PlatformSession durations (last_action_at - login_at),
    # summed in Python for SQLite/Postgres datetime portability (mirrors platform_usage).
    from app.models.platform_session import PlatformSession
    for uid, login_at, last_action_at in (
        db.query(
            PlatformSession.user_id,
            PlatformSession.login_at,
            PlatformSession.last_action_at,
        )
        .filter(PlatformSession.user_id.in_(student_ids))
        .all()
    ):
        if login_at is None or last_action_at is None:
            continue
        seconds = (last_action_at - login_at).total_seconds()
        if seconds > 0:
            metrics[uid]["total_time_on_task_min"] += seconds / 60.0

    # num_ai_interactions: assistant-role tutor chat messages per student.
    ai_rows = (
        db.query(TutorChatConversation.user_id, func.count(TutorChatMessage.id))
        .join(TutorChatMessage, TutorChatMessage.conversation_id == TutorChatConversation.id)
        .filter(
            TutorChatConversation.user_id.in_(student_ids),
            TutorChatMessage.role == "assistant",
        )
        .group_by(TutorChatConversation.user_id)
        .all()
    )
    for uid, cnt in ai_rows:
        metrics[uid]["num_ai_interactions"] = int(cnt)

    # hint_dependency_ratio numerator: hint_requested learning events per student.
    hint_rows = (
        db.query(LearningEvent.user_id, func.count(LearningEvent.id))
        .filter(
            LearningEvent.user_id.in_(student_ids),
            LearningEvent.event_type == EVENT_HINT_REQUESTED,
        )
        .group_by(LearningEvent.user_id)
        .all()
    )
    for uid, cnt in hint_rows:
        metrics[uid]["hint_count"] = int(cnt)

    # hint_dependency_ratio denominator: query attempts per student.
    attempt_rows = (
        db.query(Attempt.user_id, func.count(Attempt.id))
        .filter(Attempt.user_id.in_(student_ids))
        .group_by(Attempt.user_id)
        .all()
    )
    for uid, cnt in attempt_rows:
        metrics[uid]["attempt_count"] = int(cnt)

    # avg_solo_level_numeric: mean ordinal SOLO level per student.
    for uid, level in (
        db.query(SoloClassification.user_id, SoloClassification.solo_level)
        .filter(SoloClassification.user_id.in_(student_ids))
        .all()
    ):
        if level in _SOLO_NUMERIC:
            metrics[uid]["solo_sum"] += _SOLO_NUMERIC[level]
            metrics[uid]["solo_n"] += 1

    # scaffolding_level_at_end: level on the student's most-recently-updated conversation.
    conv_rows = (
        db.query(
            SqlTutorConversation.user_id,
            SqlTutorConversation.scaffolding_level,
            SqlTutorConversation.updated_at,
        )
        .filter(SqlTutorConversation.user_id.in_(student_ids))
        .order_by(SqlTutorConversation.user_id, SqlTutorConversation.updated_at)
        .all()
    )
    for uid, level, _updated in conv_rows:
        # Rows are ascending by updated_at, so the last one seen per user wins.
        metrics[uid]["scaffolding_level_at_end"] = level

    # error_category_counts: per-student misconception tally over both error-bearing tables.
    for model in (Attempt, LabAttempt):
        for uid, msg in (
            db.query(model.user_id, model.error_message)
            .filter(
                model.user_id.in_(student_ids),
                model.error_message.isnot(None),
                model.error_message != "",
            )
            .all()
        ):
            metrics[uid]["error_category_counts"][_classify_error(msg)] += 1

    return metrics


def stream_raw_csv_rows(db: Session):
    """Generator yielding CSV text chunks, one student row at a time. All DB aggregation
    happens once up front (batched); only the CSV serialization streams."""
    student_rows = (
        db.query(User.id, User.class_group)
        .filter(User.role == UserRole.STUDENT)
    )
    student_rows = assessment_registration.exclude_test_groups(student_rows, User.class_group)
    students = student_rows.all()
    student_ids = [uid for uid, _cg in students]

    metrics = _prefetch_all_student_metrics(db, student_ids)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_COLUMNS)
    yield buf.getvalue()
    buf.seek(0)
    buf.truncate(0)

    for uid, class_group in students:
        m = metrics[uid]
        attempts = m["attempt_count"]
        hint_ratio = round(m["hint_count"] / attempts, 4) if attempts else None
        avg_solo = round(m["solo_sum"] / m["solo_n"], 4) if m["solo_n"] else None
        writer.writerow([
            anon_id(uid),
            class_group if class_group is not None else "",
            m["final_weighted_score"] if m["final_weighted_score"] is not None else "",
            round(m["total_time_on_task_min"], 1),
            m["num_ai_interactions"],
            hint_ratio if hint_ratio is not None else "",
            avg_solo if avg_solo is not None else "",
            m["scaffolding_level_at_end"] if m["scaffolding_level_at_end"] is not None else "",
            json.dumps(dict(m["error_category_counts"])),
        ])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate(0)
