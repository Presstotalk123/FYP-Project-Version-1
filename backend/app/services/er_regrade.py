"""Regrade every stored submission of one ER question against its current rubric.

Staff run this after they edit a rubric. It is an explicit choice, never a side
effect of the edit itself, and it can be scoped to one class group. Each stored
attempt is replayed through the same submit pipeline the student used, from the
inputs the row already holds (XML first, image as fallback, plus the student's
own description and the stage/hint recorded at submit time).

The replay result replaces the row's grade in place. A staff override is
replaced too — the caller asked for a clean recalculation — so the override
markers are cleared rather than left describing a grade that no longer exists.
Rows stay append-only per attempt: no new rows are created, so attempt counts
in analytics do not move.

"Best" and "latest" are read-time concepts (assessment_scoring picks the best
row, the conversation mirrors the latest), so after the rows are rewritten this
module only has to sync each student's conversation from their latest attempt
and refresh the frozen assessment totals; the new best emerges on its own.

The job registry below is in-process, like the analytics LRU in core/cache.py.
Under several workers a status poll can miss a job started on another worker;
the run itself is still safe because every write goes through the shared DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.cache import Ns, bump_version
from app.database import SessionLocal
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.er_submission import ErSubmission
from app.models.user import User
from app.services import assessment_scoring

# Module-scope alias so tests can monkeypatch er_regrade.collect_done, the same
# by-attribute pattern the erd_tutor tests use on the runner.
from app.services.er_staff_submission import _collect_done as collect_done
from app.services.erd_tutor import persistence as erd_persistence

logger = logging.getLogger(__name__)


class RegradeAlreadyRunning(Exception):
    """A regrade for this question is still in progress."""


@dataclass
class RegradeSummary:
    total: int = 0
    regraded: int = 0
    skipped: int = 0
    failed: int = 0
    affected_users: int = 0


def _flt(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _submissions_query(db: Session, question_id: int, class_group: Optional[str]):
    query = db.query(ErSubmission).filter(
        ErSubmission.er_diagram_question_id == question_id
    )
    if class_group:
        query = query.join(User, User.id == ErSubmission.user_id).filter(
            User.class_group == class_group
        )
    return query


def count_submissions(db: Session, question_id: int, class_group: Optional[str] = None) -> int:
    """How many rows a regrade with this scope would touch — for the start guard."""
    return _submissions_query(db, question_id, class_group).count()


def _load_image_bytes(storage_key: Optional[str]) -> Optional[bytes]:
    """Bytes of a stored submission image, or None when it cannot be read.

    Local provider only, resolved exactly as the analytics image endpoint does
    (er_analytics.get_submission_image), including the traversal guard.
    """
    if not storage_key:
        return None
    if "/" in storage_key or "\\" in storage_key or ".." in storage_key:
        return None
    path = Path(settings.ER_DIAGRAM_UPLOAD_PATH) / storage_key
    if not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _write_grade(row: ErSubmission, structured: dict) -> None:
    score = structured.get("score") or {}
    checks = structured.get("checks")
    row.score_earned = _flt(score.get("earned_points"))
    row.score_total = _flt(score.get("total_points"))
    row.score_percent = _flt(score.get("percent"))
    row.score_label = str(score.get("label") or "").strip() or None
    row.checks_json = (
        json.dumps(checks, ensure_ascii=False) if isinstance(checks, list) else None
    )
    # A regrade supersedes a staff correction: the caller asked for a clean AI
    # grade under the new rubric, and the frozen "original" belongs to the old
    # one. Cleared together so `original_grade_json IS NOT NULL` keeps meaning
    # "currently overridden" for the UI badge and the revert endpoint.
    row.original_grade_json = None
    row.override_reason = None
    row.overridden_by = None
    row.overridden_at = None
    row.regraded_at = datetime.now(timezone.utc)


def _sync_conversation(
    db: Session, *, question_id: int, user_id: int,
    row: ErSubmission, structured: Optional[dict],
) -> None:
    """Mirror the student's latest attempt onto their conversation.

    The conversation is what the student sees and one of the two score sources
    assessment_scoring reads, so it must match the latest row after a regrade.
    When the latest replay succeeded, the full fresh report (new narrative
    included) is stored. When it failed, the row kept its stored grade, so the
    score/checks are mirrored from the columns and the old narrative is kept —
    the er_score_override merge rule.
    """
    conv = erd_persistence.find_conversation(
        db, user_id=user_id, er_diagram_question_id=question_id
    )
    if conv is None:
        return

    if structured is not None:
        conv.last_submit_score = json.dumps(structured.get("score") or {}, ensure_ascii=False)
        conv.last_submit_report = json.dumps(structured, ensure_ascii=False)
        return

    score = {
        "label": row.score_label,
        "earned_points": row.score_earned,
        "total_points": row.score_total,
        "percent": row.score_percent,
    }
    try:
        checks = json.loads(row.checks_json) if row.checks_json else []
    except (TypeError, ValueError):
        checks = []
    conv.last_submit_score = json.dumps(score, ensure_ascii=False)
    try:
        report = json.loads(conv.last_submit_report or "{}")
    except (TypeError, ValueError):
        report = {}
    if not isinstance(report, dict):
        report = {}
    report["score"] = score
    report["checks"] = checks
    conv.last_submit_report = json.dumps(report, ensure_ascii=False)


async def regrade_submissions(
    db: Session,
    *,
    question: ERDiagramQuestion,
    class_group: Optional[str] = None,
    on_total: Optional[Callable[[int], None]] = None,
    on_row: Optional[Callable[[str], None]] = None,
) -> RegradeSummary:
    """Replay and rewrite every stored submission for one question.

    Sequential on purpose: one LLM run at a time bounds cost and load, and the
    single DB session is never touched concurrently. Each row commits on its
    own, so an interrupted run keeps every grade it already produced and a
    re-run simply continues over the same rows.
    """
    rows = (
        _submissions_query(db, question.id, class_group)
        .order_by(ErSubmission.user_id, ErSubmission.created_at, ErSubmission.id)
        .all()
    )
    summary = RegradeSummary(total=len(rows))
    if on_total:
        on_total(len(rows))

    # Ordered by (user, created_at, id), so the last row seen per user is their
    # latest attempt — the one the conversation must mirror.
    latest: dict[int, tuple[ErSubmission, Optional[dict]]] = {}
    changed_users: set[int] = set()

    for row in rows:
        xml_text = (row.submitted_xml or "").strip() or None
        # Both sources, exactly as the live submit sends them. The pipeline
        # prefers the XML, but when parse_drawio rejects it (measured on real
        # rows: "no ERD structure found") observe_node falls back to vision —
        # and with no image that fallback grades an empty diagram as 0.
        image_bytes = _load_image_bytes(row.submitted_image_storage_key)
        structured: Optional[dict] = None

        if not xml_text and not image_bytes:
            summary.skipped += 1
            outcome = "skipped"
        else:
            try:
                done = await collect_done(
                    question=question,
                    xml_text=xml_text,
                    image_bytes=image_bytes,
                    ibl_stage=row.ibl_stage_at_submit or "orientation",
                    hint_level=row.hint_level_at_submit or 1,
                    # Never a previous report: regrades replay out of order, and
                    # cross-attempt progress deltas would poison the grade text.
                    last_report={},
                    submission_description=row.submission_description,
                )
                structured = (done or {}).get("structured_output") or None
                if structured is None or (structured.get("score") or {}).get("percent") is None:
                    structured = None
                    raise RuntimeError("pipeline returned no grade")
                _write_grade(row, structured)
                db.commit()
                summary.regraded += 1
                changed_users.add(row.user_id)
                outcome = "regraded"
            except Exception as exc:
                db.rollback()
                structured = None
                summary.failed += 1
                outcome = "failed"
                logger.warning(
                    "er_regrade: submission %s (user %s, question %s) failed: %s",
                    row.id, row.user_id, question.id, exc,
                )

        latest[row.user_id] = (row, structured)
        if on_row:
            on_row(outcome)

    for uid in sorted(changed_users):
        row, structured = latest[uid]
        _sync_conversation(
            db, question_id=question.id, user_id=uid, row=row, structured=structured
        )
        # Never raises; recomputes the frozen assessment total for a completed
        # attempt. Reads the conversation, so the sync above must come first.
        assessment_scoring.refresh_frozen_weighted_score(
            db, er_question_id=question.id, user_id=uid
        )
    summary.affected_users = len(changed_users)

    if changed_users:
        # The materialized assessment averages are deliberately not invalidated
        # by submission/conversation writes (see core/cache.py), so bump them
        # here; ER analytics is bumped too so a stale worker cannot serve the
        # old aggregates after the run.
        bump_version(db, Ns.ASSESSMENT_ANALYTICS)
        bump_version(db, Ns.ER_ANALYTICS)
    db.commit()
    return summary


# --- In-process job registry ------------------------------------------------------


@dataclass
class RegradeJob:
    question_id: int
    class_group: Optional[str]
    status: str = "running"  # running | done | failed
    total: int = 0
    completed: int = 0
    regraded: int = 0
    skipped: int = 0
    failed: int = 0
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def snapshot(self) -> dict:
        return {
            "question_id": self.question_id,
            "class_group": self.class_group,
            "status": self.status,
            "total": self.total,
            "completed": self.completed,
            "regraded": self.regraded,
            "skipped": self.skipped,
            "failed": self.failed,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


_jobs: dict[int, RegradeJob] = {}


def job_status(question_id: int) -> Optional[dict]:
    job = _jobs.get(question_id)
    return job.snapshot() if job else None


def start_regrade(
    question_id: int,
    class_group: Optional[str],
    *,
    session_factory: Callable[[], Session] = SessionLocal,
) -> dict:
    """Start a background regrade for one question; returns the initial snapshot.

    One job per question at a time. The task owns its own DB session — the
    request's session closes when the response goes out.
    """
    existing = _jobs.get(question_id)
    if existing is not None and existing.status == "running":
        raise RegradeAlreadyRunning(
            "A regrade for this question is already running."
        )
    job = RegradeJob(
        question_id=question_id,
        class_group=class_group,
        started_at=datetime.now(timezone.utc),
    )
    _jobs[question_id] = job
    asyncio.get_running_loop().create_task(_run_job(job, session_factory))
    return job.snapshot()


async def _run_job(job: RegradeJob, session_factory: Callable[[], Session]) -> None:
    db = session_factory()
    try:
        question = (
            db.query(ERDiagramQuestion)
            .filter(ERDiagramQuestion.id == job.question_id)
            .first()
        )
        if question is None:
            raise RuntimeError("Question not found")

        def on_total(n: int) -> None:
            job.total = n

        def on_row(outcome: str) -> None:
            job.completed += 1
            if outcome == "regraded":
                job.regraded += 1
            elif outcome == "skipped":
                job.skipped += 1
            else:
                job.failed += 1

        await regrade_submissions(
            db,
            question=question,
            class_group=job.class_group,
            on_total=on_total,
            on_row=on_row,
        )
        job.status = "done"
    except Exception as exc:
        logger.exception("er_regrade: job for question %s failed", job.question_id)
        job.status = "failed"
        job.error = str(exc)
    finally:
        job.finished_at = datetime.now(timezone.utc)
        db.close()
