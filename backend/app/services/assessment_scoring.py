"""Weighted assessment scoring.

Combines a student's per-item activity into a single weighted score (0-100) using the
per-question `weight` set by staff. Each item type yields a correctness fraction (0.0-1.0):

- sql_question: 1.0 if the student has any correct attempt, else 0.0 (binary).
- sql_lab / graph_lab: distinct correct tasks / total tasks.
- er_question: the latest LLM-graded percent / 100 (from the ERD tutor conversation).

The weighted total is Σ(weight_i * fraction_i) normalised to 100 so it stays a percentage
even if the stored weights don't sum to exactly 100. Returns None when the assessment has
no weightage at all (legacy/unweighted), so callers can show "N/A" instead of a false 0.
"""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.cache import Ns, cache_read, get_version
from app.models.assessment import Assessment
from app.models.assessment_analytics import AssessmentAnalytics
from app.models.assessment_class_window import AssessmentClassWindow
from app.models.assessment_item import AssessmentItem
from app.models.assessment_item_visit import AssessmentItemVisit
from app.models.assessment_session import AssessmentSession
from app.models.attempt import Attempt
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.lab import Lab
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.question import Question
from app.models.user import User
from app.schemas.assessment import (
    AssessmentItemAggregateScore,
    LabTaskAggregateScore,
)
from app.services.erd_tutor import persistence as erd_persistence


def _percent_from_score_json(last_submit_score: Optional[str]) -> Optional[float]:
    """Parse the `percent` (0-100) out of an ERD-tutor `last_submit_score` JSON string."""
    if not last_submit_score:
        return None
    try:
        data = json.loads(last_submit_score)
    except (ValueError, TypeError):
        return None
    try:
        return float(data.get("percent"))
    except (TypeError, ValueError):
        return None


def er_percent(db: Session, question_id: int, student_id: int) -> Optional[float]:
    """Latest LLM-graded percent (0-100) for a student's assessment ER question, or None.

    Assessment ER questions go through the standalone ERD-tutor path, which keeps a single
    conversation per (user, question) with the latest grade in `last_submit_score` JSON.
    """
    conv = erd_persistence.find_conversation(
        db,
        user_id=student_id,
        context_type="standalone",
        er_diagram_question_id=question_id,
    )
    if not conv:
        return None
    return _percent_from_score_json(conv.last_submit_score)


@dataclass
class ItemScoreDetail:
    """Per-student, per-item scoring detail: the correctness fraction plus the raw
    per-type fields needed to render an activity breakdown (attempt counts, lab task
    counts, ER visit status)."""
    fraction: float
    has_correct_attempt: Optional[bool] = None
    attempt_count: Optional[int] = None
    visited: Optional[bool] = None
    tasks_correct: Optional[int] = None
    tasks_total: Optional[int] = None
    # The specific task ids this student solved (lab items only) — lets callers tally
    # per-task success rates across a roster without an extra query.
    correct_task_ids: Optional[set] = None


def item_score_detail(
    db: Session,
    item: AssessmentItem,
    student_id: int,
    session_id: Optional[int] = None,
) -> ItemScoreDetail:
    """Correctness fraction (0.0-1.0) and raw activity detail for a single assessment item.

    `session_id` (the student's AssessmentSession.id) is only used for the er_question
    "visited" flag; pass None when that detail isn't needed.
    """
    if item.item_type == "sql_question":
        attempts = (
            db.query(Attempt)
            .filter(Attempt.user_id == student_id, Attempt.question_id == item.item_id)
            .all()
        )
        has_correct = any(bool(a.is_correct) for a in attempts)
        return ItemScoreDetail(
            fraction=1.0 if has_correct else 0.0,
            has_correct_attempt=has_correct,
            attempt_count=len(attempts),
        )

    if item.item_type in ("sql_lab", "graph_lab"):
        total_tasks = (
            db.query(LabTask)
            .filter(LabTask.lab_id == item.item_id, LabTask.is_deleted == 0)
            .count()
        )
        correct_task_ids = {
            row[0] for row in (
                db.query(LabTaskSubmission.task_id)
                .filter(
                    LabTaskSubmission.user_id == student_id,
                    LabTaskSubmission.lab_id == item.item_id,
                    LabTaskSubmission.is_correct == 1,
                )
                .distinct()
                .all()
            )
        }
        correct_tasks = len(correct_task_ids)
        fraction = min(1.0, correct_tasks / total_tasks) if total_tasks > 0 else 0.0
        return ItemScoreDetail(
            fraction=fraction,
            tasks_correct=correct_tasks,
            tasks_total=total_tasks,
            correct_task_ids=correct_task_ids,
        )

    if item.item_type == "er_question":
        visited = False
        if session_id is not None:
            visited = (
                db.query(AssessmentItemVisit)
                .filter(
                    AssessmentItemVisit.session_id == session_id,
                    AssessmentItemVisit.assessment_item_id == item.id,
                )
                .first()
            ) is not None
        pct = er_percent(db, item.item_id, student_id)
        return ItemScoreDetail(
            fraction=(pct / 100.0) if pct is not None else 0.0,
            visited=visited,
        )

    return ItemScoreDetail(fraction=0.0)


def item_score_fraction(db: Session, item: AssessmentItem, student_id: int) -> float:
    """Correctness fraction (0.0-1.0) for a single assessment item."""
    return item_score_detail(db, item, student_id).fraction


def compute_weighted_score(db: Session, assessment: Assessment, student_id: int) -> Optional[float]:
    """Weighted total (0-100) for a student, or None if the assessment carries no weightage."""
    items = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.assessment_id == assessment.id)
        .all()
    )
    total_weight = sum(i.weight for i in items)
    if total_weight <= 0:
        return None
    earned = sum(i.weight * item_score_fraction(db, i, student_id) for i in items)
    return round(earned / total_weight * 100, 1)


def roster_user_ids(
    db: Session, assessment_id: int, class_group: Optional[str] = None
) -> list[int]:
    """Distinct user ids of everyone who has a session on this assessment.

    The whole cohort for cohort-average purposes — mirrors the endpoint's
    `_student_roster` but returns ids only (one row per user is implicit in the
    distinct set, so the "latest session per user" collapse isn't needed here).
    Pass `class_group` to restrict to a single group (the class-group roster).
    """
    query = (
        db.query(AssessmentSession.user_id)
        .filter(AssessmentSession.assessment_id == assessment_id)
    )
    if class_group:
        query = query.join(User, User.id == AssessmentSession.user_id).filter(
            User.class_group == class_group
        )
    rows = query.distinct().all()
    return [uid for (uid,) in rows]


@dataclass
class RosterAnalytics:
    """Fully-aggregated analytics for one roster (whole cohort, or one class_group).

    Computed in a handful of bulk queries by `compute_roster_analytics`, this is the
    single shared result every report reads: the per-item/per-task breakdown, the
    overall weighted average, and each student's weighted total.
    """
    assessment_id: int
    class_group: Optional[str]
    student_count: int
    # Mean weighted total (0-100) across the roster; None if unweighted or empty.
    avg_weighted_score: Optional[float]
    items: list = field(default_factory=list)  # list[AssessmentItemAggregateScore]
    # user_id -> weighted total (0-100), or None when the assessment is unweighted.
    per_student_scores: dict = field(default_factory=dict)


def compute_roster_analytics(
    db: Session, assessment: Assessment, class_group: Optional[str] = None
) -> RosterAnalytics:
    """Aggregate every per-item / per-task / cohort number for a roster in a few bulk
    queries — the batched replacement for the per-(student, item) `item_score_detail`
    fan-out in the item-analytics endpoint and `cohort_average`.

    The math is identical to the legacy paths (per-item mean fractions weighted to 100,
    per-student weighted totals rounded to 0.1), so results are unchanged.
    """
    items = (
        db.query(AssessmentItem)
        .filter(AssessmentItem.assessment_id == assessment.id)
        .order_by(AssessmentItem.order_index)
        .all()
    )
    student_ids = roster_user_ids(db, assessment.id, class_group)
    n = len(student_ids)

    sql_q_ids = [i.item_id for i in items if i.item_type == "sql_question"]
    lab_ids = [i.item_id for i in items if i.item_type in ("sql_lab", "graph_lab")]
    er_q_ids = [i.item_id for i in items if i.item_type == "er_question"]

    # --- SQL questions: set of (user, question) with any correct attempt (binary) ---
    solved_sql: set = set()
    if student_ids and sql_q_ids:
        solved_sql = {
            (uid, qid)
            for uid, qid in db.query(Attempt.user_id, Attempt.question_id)
            .filter(
                Attempt.user_id.in_(student_ids),
                Attempt.question_id.in_(sql_q_ids),
                Attempt.is_correct == 1,
            )
            .distinct()
            .all()
        }

    # --- Labs: total tasks per lab, and each student's solved-task set per lab ---
    lab_total_tasks: dict = {}
    if lab_ids:
        lab_total_tasks = dict(
            db.query(LabTask.lab_id, func.count(LabTask.id))
            .filter(LabTask.lab_id.in_(lab_ids), LabTask.is_deleted == 0)
            .group_by(LabTask.lab_id)
            .all()
        )
    lab_solved: dict = defaultdict(set)  # (user_id, lab_id) -> {task_id}
    if student_ids and lab_ids:
        for uid, lid, tid in (
            db.query(
                LabTaskSubmission.user_id,
                LabTaskSubmission.lab_id,
                LabTaskSubmission.task_id,
            )
            .filter(
                LabTaskSubmission.user_id.in_(student_ids),
                LabTaskSubmission.lab_id.in_(lab_ids),
                LabTaskSubmission.is_correct == 1,
            )
            .distinct()
            .all()
        ):
            lab_solved[(uid, lid)].add(tid)

    # --- ER questions: latest graded percent per (user, question) ---
    er_percents: dict = {}  # (user_id, question_id) -> percent (0-100) or None
    if student_ids and er_q_ids:
        raw = erd_persistence.find_last_submit_scores_bulk(
            db, user_ids=student_ids, er_diagram_question_ids=er_q_ids
        )
        er_percents = {key: _percent_from_score_json(s) for key, s in raw.items()}

    item_rows: list = []
    total_weight = 0
    weighted_avg_earned = 0.0
    per_student_earned = {uid: 0.0 for uid in student_ids}

    for item in items:
        title = resolve_item_title(db, item)
        fractions: list = []
        avg_tasks_correct: Optional[float] = None
        tasks_total: Optional[int] = None
        task_rows: Optional[list] = None

        if item.item_type == "sql_question":
            fractions = [
                1.0 if (uid, item.item_id) in solved_sql else 0.0
                for uid in student_ids
            ]
        elif item.item_type in ("sql_lab", "graph_lab"):
            total = lab_total_tasks.get(item.item_id, 0)
            tasks_total = total
            tasks_correct_values: list = []
            task_correct_counts: dict = defaultdict(int)
            for uid in student_ids:
                solved = lab_solved.get((uid, item.item_id), set())
                correct = len(solved)
                fractions.append(min(1.0, correct / total) if total > 0 else 0.0)
                tasks_correct_values.append(correct)
                for tid in solved:
                    task_correct_counts[tid] += 1
            avg_tasks_correct = (
                round(sum(tasks_correct_values) / len(tasks_correct_values), 2)
                if tasks_correct_values else None
            )
            lab_tasks = (
                db.query(LabTask)
                .filter(LabTask.lab_id == item.item_id, LabTask.is_deleted == 0)
                .order_by(LabTask.order_index)
                .all()
            )
            task_rows = [
                LabTaskAggregateScore(
                    task_id=task.id,
                    task_title=task.title,
                    order_index=task.order_index,
                    success_rate=(
                        round(task_correct_counts.get(task.id, 0) / n * 100, 1)
                        if n else None
                    ),
                )
                for task in lab_tasks
            ]
        elif item.item_type == "er_question":
            for uid in student_ids:
                pct = er_percents.get((uid, item.item_id))
                fractions.append((pct / 100.0) if pct is not None else 0.0)
        else:
            fractions = [0.0 for _ in student_ids]

        avg_fraction = round(sum(fractions) / len(fractions), 4) if fractions else None
        avg_weighted_points = (
            round(item.weight * avg_fraction, 2) if avg_fraction is not None else None
        )

        for idx, uid in enumerate(student_ids):
            per_student_earned[uid] += item.weight * fractions[idx]

        item_rows.append(AssessmentItemAggregateScore(
            assessment_item_id=item.id,
            item_type=item.item_type,
            item_id=item.item_id,
            item_title=title,
            order_index=item.order_index,
            weight=item.weight,
            avg_score_fraction=avg_fraction,
            avg_weighted_points=avg_weighted_points,
            avg_tasks_correct=avg_tasks_correct,
            tasks_total=tasks_total,
            tasks=task_rows,
        ))

        total_weight += item.weight
        weighted_avg_earned += item.weight * (avg_fraction or 0.0)

    avg_weighted_score = (
        round(weighted_avg_earned / total_weight * 100, 1)
        if total_weight > 0 and student_ids
        else None
    )
    per_student_scores = {
        uid: (round(earned / total_weight * 100, 1) if total_weight > 0 else None)
        for uid, earned in per_student_earned.items()
    }

    return RosterAnalytics(
        assessment_id=assessment.id,
        class_group=class_group,
        student_count=n,
        avg_weighted_score=avg_weighted_score,
        items=item_rows,
        per_student_scores=per_student_scores,
    )


# --- Cache-over-table accessor ---------------------------------------------------

def _serialize_analytics(result: RosterAnalytics) -> str:
    """RosterAnalytics -> JSON string for the assessment_analytics.payload column."""
    return json.dumps({
        "class_group": result.class_group,
        "student_count": result.student_count,
        "avg_weighted_score": result.avg_weighted_score,
        "items": [item.model_dump() for item in result.items],
        # JSON object keys must be strings; restored to int on read.
        "per_student_scores": {str(uid): s for uid, s in result.per_student_scores.items()},
    })


def _deserialize_analytics(assessment_id: int, payload: str) -> RosterAnalytics:
    data = json.loads(payload)
    return RosterAnalytics(
        assessment_id=assessment_id,
        class_group=data.get("class_group"),
        student_count=data.get("student_count", 0),
        avg_weighted_score=data.get("avg_weighted_score"),
        items=[AssessmentItemAggregateScore.model_validate(i) for i in data.get("items", [])],
        per_student_scores={int(uid): s for uid, s in data.get("per_student_scores", {}).items()},
    )


def _load_analytics_row(db: Session, assessment_id: int, class_group: Optional[str]):
    query = db.query(AssessmentAnalytics).filter(
        AssessmentAnalytics.assessment_id == assessment_id
    )
    if class_group is None:
        query = query.filter(AssessmentAnalytics.class_group.is_(None))
    else:
        query = query.filter(AssessmentAnalytics.class_group == class_group)
    return query.first()


def _persist_analytics(
    db: Session, assessment_id: int, class_group: Optional[str],
    result: RosterAnalytics, version: int,
) -> None:
    """Write the materialized row in its OWN short-lived session.

    Deliberately a distinct Session (not the request session): SessionLocal defaults to
    expire_on_commit=True, so committing on the request session would expire every ORM
    object a read endpoint already loaded (e.g. the student roster), silently
    re-querying them. Because expire_on_commit only affects the committing session's own
    identity map, a separate Session leaves the request session's objects untouched.
    It is bound to the request session's engine (`db.get_bind()`) so it writes to the
    same database in prod AND under the tests' isolated in-memory engine. Writing
    AssessmentAnalytics maps to no cache namespace, so its flush does not bump
    ASSESSMENT_ANALYTICS (no self-invalidation).
    """
    payload = _serialize_analytics(result)
    now = datetime.utcnow()
    w = Session(bind=db.get_bind())
    try:
        row = _load_analytics_row(w, assessment_id, class_group)
        if row is None:
            w.add(AssessmentAnalytics(
                assessment_id=assessment_id,
                class_group=class_group,
                student_count=result.student_count,
                avg_weighted_score=result.avg_weighted_score,
                payload=payload,
                version=version,
                computed_at=now,
            ))
        else:
            row.student_count = result.student_count
            row.avg_weighted_score = result.avg_weighted_score
            row.payload = payload
            row.version = version
            row.computed_at = now
        w.commit()
    except Exception:
        # A concurrent worker may have inserted the same (assessment, class_group) row
        # first (partial unique index race), or the write may transiently fail. Never
        # fail a read over a cache write — the row will be (re)materialized on a later
        # read; the freshly computed result is still returned to this caller.
        w.rollback()
    finally:
        w.close()


def _materialize(db: Session, assessment: Assessment, class_group: Optional[str]) -> RosterAnalytics:
    """L2 (durable table) + L3 (recompute) behind the in-process cache.

    Serves the stored row when its version matches the current ASSESSMENT_ANALYTICS
    generation; otherwise recomputes in bulk, persists the row, and returns it. The
    request session stays read-only throughout (the write goes through its own session).
    """
    cur = get_version(db, Ns.ASSESSMENT_ANALYTICS)
    if cur < 0:
        # Cache subsystem / table unavailable -> compute live, don't persist.
        return compute_roster_analytics(db, assessment, class_group)

    row = _load_analytics_row(db, assessment.id, class_group)
    if row is not None and row.version == cur:
        return _deserialize_analytics(assessment.id, row.payload)

    result = compute_roster_analytics(db, assessment, class_group)
    _persist_analytics(db, assessment.id, class_group, result, cur)
    return result


def _still_accepting_submissions(db: Session, assessment: Assessment) -> bool:
    """True while the assessment can still receive submissions, so its analytics are not
    yet final. Manual run: `is_running`. Timing Gateway: any enabled window whose end is
    still in the future. While this holds, analytics are computed live (never cached), so
    a mid-assessment read reflects current data instead of freezing a preliminary
    snapshot; once the assessment closes, the version-gated cache/table takes over."""
    if assessment.is_running:
        return True
    if assessment.gateway_enabled:
        now = datetime.now(timezone.utc)
        ends = (
            db.query(AssessmentClassWindow.end_at)
            .filter(
                AssessmentClassWindow.assessment_id == assessment.id,
                AssessmentClassWindow.is_enabled == 1,
            )
            .all()
        )
        for (end_at,) in ends:
            end = end_at if end_at.tzinfo else end_at.replace(tzinfo=timezone.utc)
            if now < end:
                return True
    return False


def get_or_compute_analytics(
    db: Session, assessment: Assessment, class_group: Optional[str] = None
) -> RosterAnalytics:
    """Shared, compute-once analytics for a roster (whole cohort or one class_group).

    While the assessment is still open, results are not final and students keep
    submitting, so compute fresh on each (rare, read-driven) request rather than caching
    a snapshot that would otherwise freeze at first view. Once it closes, serve through
    three layers keyed by (assessment_id, class_group), all gated by the
    ASSESSMENT_ANALYTICS version: L1 in-process cache -> L2 assessment_analytics table
    -> L3 bulk recompute, so the final aggregate is computed once and reused.
    """
    if _still_accepting_submissions(db, assessment):
        return compute_roster_analytics(db, assessment, class_group)

    return cache_read(
        db,
        Ns.ASSESSMENT_ANALYTICS,
        key=(assessment.id, class_group),
        producer=lambda: _materialize(db, assessment, class_group),
    )


def roster_class_groups(db: Session, assessment_id: int) -> list[str]:
    """Distinct, non-null class_groups actually present in this assessment's roster —
    used to eager-materialize each group's analytics (not every group in the system,
    just the ones with students on this assessment)."""
    rows = (
        db.query(User.class_group)
        .join(AssessmentSession, AssessmentSession.user_id == User.id)
        .filter(
            AssessmentSession.assessment_id == assessment_id,
            User.class_group.isnot(None),
        )
        .distinct()
        .all()
    )
    return [cg for (cg,) in rows if cg]


def warm_analytics_cache(db: Session, assessment: Assessment) -> None:
    """Eagerly compute and persist the cohort-wide analytics plus every class_group
    present in the roster, right after a data-changing event (assessment stop, a
    student reset) instead of waiting for the first report view to pay the cost.

    Best-effort: a failure here must never fail the caller's action (stopping the
    assessment, resetting a student). If warming fails or is skipped, the first
    viewer's request simply falls back to the normal lazy compute-on-read path.
    """
    try:
        get_or_compute_analytics(db, assessment, class_group=None)
        for cg in roster_class_groups(db, assessment.id):
            get_or_compute_analytics(db, assessment, class_group=cg)
    except Exception:
        pass


def cohort_average(db: Session, assessment: Assessment) -> Optional[float]:
    """Mean weighted score (0-100) across everyone who took the assessment.

    Reads the shared, cached cohort analytics (compute-once) instead of recomputing
    every student's weighted total on each call. Returns None when the assessment is
    unweighted or no student has a scorable weighted total.
    """
    analytics = get_or_compute_analytics(db, assessment, class_group=None)
    scores = [s for s in analytics.per_student_scores.values() if s is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 1)


def resolve_item_title(db: Session, item: AssessmentItem) -> str:
    """Display title for a polymorphic assessment item (SQL/ER question or lab)."""
    if item.item_type == "sql_question":
        row = db.query(Question.title).filter(Question.id == item.item_id).first()
        return row[0] if row else f"Question #{item.item_id}"
    if item.item_type == "er_question":
        row = db.query(ERDiagramQuestion.title).filter(ERDiagramQuestion.id == item.item_id).first()
        return row[0] if row else f"ER Question #{item.item_id}"
    if item.item_type in ("sql_lab", "graph_lab"):
        row = db.query(Lab.title).filter(Lab.id == item.item_id, Lab.is_deleted == 0).first()
        return row[0] if row else f"Lab #{item.item_id}"
    return f"Item #{item.item_id}"
