"""
In-process, DB-version-stamped read cache for data that is identical across all
staff/admin (and, per role, across all students).

Why this exists
---------------
The staff pages (Problems, Manage Labs, Assessments, ...) and several student
lists re-run the same DB query + serialization on every page load, per user. The
frontend React Query layer only de-duplicates within one browser session; it does
nothing across users or on first load. This module caches those payloads in the
worker's memory.

How freshness works across gunicorn workers (no Redis)
------------------------------------------------------
Each cached payload is tagged with a generation number stored in a shared DB table
(`cache_versions`, one row per namespace). A read compares its cached version with
the DB version (one trivial single-row PK read on the *request's* session):
  - equal   -> serve the in-memory payload (skip the heavy query + serialization)
  - differ  -> recompute once, store (version, payload)
A mutation bumps the DB version *in the same transaction* as the write. Because the
version row lives in the shared DB, every worker sees the bump on its next read, so
no worker can serve data older than the last committed mutation -- instant
cross-worker consistency with no TTL staleness window.

Invalidation is automatic: `register_invalidation_events()` installs an
`after_flush` SQLAlchemy listener that bumps the right namespace whenever a mapped
row changes. The only manual bumps needed are for bulk `update()`/`delete()` calls,
which bypass the ORM unit of work (see `bump_version`).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable

from sqlalchemy import BigInteger, Column, String, event, text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal


# --- Version table model --------------------------------------------------------

class CacheVersion(Base):
    """
    Generation counter per cache namespace. Registered on Base so that any path
    that builds the schema from metadata (SQLite local dev, the test suite) creates
    it automatically; `bootstrap()` additionally guarantees it on Postgres, where
    the schema is provisioned out-of-band.
    """
    __tablename__ = "cache_versions"

    name = Column(String(64), primary_key=True)
    version = Column(BigInteger, nullable=False, default=0)


# --- Namespaces -----------------------------------------------------------------

class Ns:
    """Cache namespaces. One `cache_versions` row per value here."""
    QUESTIONS = "questions"
    LABS = "labs"
    ER_QUESTIONS = "er_questions"
    ASSESSMENTS = "assessments"
    ERD_PROMPTS = "erd_prompts"
    ER_ANALYTICS = "er_analytics"
    SQL_ANALYTICS = "sql_analytics"
    LAB_ANALYTICS = "lab_analytics"
    COURSE_INFO = "course_info"
    WHITELIST = "whitelist"


# Static namespaces that get a seed row on startup. `assessment_body:{id}` rows are
# created lazily on first bump (get_version treats a missing row as version 0).
ALL_NAMESPACES: tuple[str, ...] = (
    Ns.QUESTIONS,
    Ns.LABS,
    Ns.ER_QUESTIONS,
    Ns.ASSESSMENTS,
    Ns.ERD_PROMPTS,
    Ns.ER_ANALYTICS,
    Ns.SQL_ANALYTICS,
    Ns.LAB_ANALYTICS,
    Ns.COURSE_INFO,
    Ns.WHITELIST,
)


def assessment_body_ns(assessment_id: int) -> str:
    """Namespace for a single running assessment's cached body."""
    return f"assessment_body:{assessment_id}"


# --- In-memory store ------------------------------------------------------------

# namespace -> LRU(key -> (version, payload)). Sized so a namespace can hold its list
# variants plus many per-id detail entries (question/lab/ER detail, lab tasks) without
# thrashing during an assessment.
_LRU_MAXSIZE = 256
_store: dict[str, "OrderedDict[tuple, tuple[int, Any]]"] = {}
# Per-(namespace, key) lock for single-flight; guarded by _lock while created.
_key_locks: dict[tuple[str, tuple], threading.Lock] = {}
_lock = threading.Lock()

# Set True by bootstrap() once the cache_versions table is known to exist. Until
# then the after_flush listener must not issue bumps (a missing table would raise
# inside a real mutation's flush and, on Postgres, poison its transaction).
_cache_ready = False


def _get_cached(namespace: str, key: tuple) -> tuple[int, Any] | None:
    with _lock:
        ns = _store.get(namespace)
        if ns is None:
            return None
        entry = ns.get(key)
        if entry is not None:
            ns.move_to_end(key)  # LRU touch
        return entry


def _put_cached(namespace: str, key: tuple, version: int, payload: Any) -> None:
    with _lock:
        ns = _store.get(namespace)
        if ns is None:
            ns = OrderedDict()
            _store[namespace] = ns
        existing = ns.get(key)
        # Never let a slow thread stamped with an older version clobber a newer entry.
        if existing is not None and existing[0] > version:
            return
        ns[key] = (version, payload)
        ns.move_to_end(key)
        while len(ns) > _LRU_MAXSIZE:
            ns.popitem(last=False)


def _key_lock(namespace: str, key: tuple) -> threading.Lock:
    kk = (namespace, key)
    with _lock:
        kl = _key_locks.get(kk)
        if kl is None:
            kl = threading.Lock()
            _key_locks[kk] = kl
        return kl


# --- Version table access -------------------------------------------------------

def get_version(db: Session, namespace: str) -> int:
    """
    Read the current generation for a namespace. Single-row PK lookup on the
    request's existing session (no extra pool checkout). A missing table/row
    returns 0 -- cache infrastructure must never 500 a read.
    """
    try:
        row = db.execute(
            text("SELECT version FROM cache_versions WHERE name = :n"),
            {"n": namespace},
        ).first()
        return int(row[0]) if row is not None else 0
    except Exception:
        # Table not present yet, or any transient issue -> behave as a permanent
        # miss so the caller falls through to the live query.
        return -1


def bump_version(db: Session, namespace: str) -> None:
    """
    Invalidate a namespace by incrementing its generation. Call this *before*
    `db.commit()` in a mutation so the bump commits atomically with the change.

    Only needed explicitly for bulk `update()`/`delete()` that bypass the ORM unit
    of work; ordinary ORM attribute mutations are handled by the after_flush event.

    Uses a single atomic upsert so a lazily-created namespace (e.g.
    assessment_body:{id}) works and concurrent first-bumps can't race into an
    IntegrityError — critical because this runs inside the mutation's transaction,
    where a failed statement would poison the whole commit on PostgreSQL. The
    `ON CONFLICT ... DO UPDATE` form is supported by both PostgreSQL and SQLite (3.24+).
    """
    db.execute(
        text(
            "INSERT INTO cache_versions (name, version) VALUES (:n, 1) "
            "ON CONFLICT (name) DO UPDATE SET version = cache_versions.version + 1"
        ),
        {"n": namespace},
    )


# --- Cache-aside read -----------------------------------------------------------

def cache_read(
    db: Session,
    namespace: str,
    key: tuple,
    producer: Callable[[], Any],
    *,
    cacheable: bool = True,
) -> Any:
    """
    Cache-aside read.

    - `producer()` must run the real query AND fully serialize the result while the
      session is open (return Pydantic models / plain dicts, never session-bound ORM
      rows -- those raise DetachedInstanceError once the request session closes).
    - Reads the version BEFORE calling producer(): if a mutation commits in between,
      the fresh payload is stamped with the older version and simply discarded on the
      next access (monotonic versions), never served stale.
    - Single-flight: concurrent misses on the same key collapse into one producer()
      call.
    """
    if not cacheable:
        return producer()

    version = get_version(db, namespace)
    if version < 0:
        # Cache subsystem unavailable -> always run live.
        return producer()

    entry = _get_cached(namespace, key)
    if entry is not None and entry[0] == version:
        return entry[1]

    # Miss -> single-flight so the herd computes once.
    kl = _key_lock(namespace, key)
    with kl:
        # Another thread may have filled it while we waited.
        entry = _get_cached(namespace, key)
        if entry is not None and entry[0] == version:
            return entry[1]
        payload = producer()
        _put_cached(namespace, key, version, payload)
        return payload


# --- Automatic invalidation -----------------------------------------------------

def _model_namespaces(obj: Any) -> set[str]:
    """Map a changed ORM instance to the cache namespace(s) it invalidates."""
    # Imported lazily to avoid import cycles at module load.
    from app.models.question import Question
    from app.models.lab import Lab
    from app.models.lab_task import LabTask
    from app.models.er_diagram_question import ERDiagramQuestion
    from app.models.er_submission import ErSubmission
    from app.models.erd_tutor_message import ErdTutorMessage
    from app.models.assessment import Assessment
    from app.models.assessment_item import AssessmentItem
    from app.models.user import User
    from app.models.course_info import CourseInfo
    from app.models.attempt import Attempt
    from app.models.progress import UserProgress
    from app.models.lab_attempt import LabAttempt
    from app.models.lab_task_submission import LabTaskSubmission
    from app.models.query_review import QueryReview
    from app.models.tutor_chat_conversation import TutorChatConversation
    from app.models.tutor_chat_message import TutorChatMessage
    from app.models.whitelist import WhitelistEntry

    namespaces: set[str] = set()

    if isinstance(obj, WhitelistEntry):
        return {Ns.WHITELIST}

    if isinstance(obj, Question):
        namespaces.add(Ns.QUESTIONS)
        namespaces.add(Ns.SQL_ANALYTICS)  # analytics show the question title
    # Staff analytics aggregate submissions, chat messages (query topics) and
    # user class groups, so any of those changing must invalidate the payloads.
    if isinstance(obj, (ErSubmission, ErdTutorMessage, User)):
        namespaces.add(Ns.ER_ANALYTICS)
    # SQL-question analytics aggregate attempts, progress, persisted query reviews,
    # tutor-chat usage and user class groups.
    if isinstance(obj, (Attempt, UserProgress, QueryReview,
                        TutorChatConversation, TutorChatMessage, User)):
        namespaces.add(Ns.SQL_ANALYTICS)
    # Lab analytics aggregate lab attempts/submissions, persisted query reviews,
    # tutor-chat usage and user class groups.
    if isinstance(obj, (LabAttempt, LabTaskSubmission, QueryReview,
                        TutorChatConversation, TutorChatMessage, User)):
        namespaces.add(Ns.LAB_ANALYTICS)
    if namespaces:
        return namespaces
    if isinstance(obj, CourseInfo):
        return {Ns.COURSE_INFO}
    # A lab's cached detail and its cached task list both live under Ns.LABS, so a
    # LabTask change must invalidate that namespace too.
    if isinstance(obj, (Lab, LabTask)):
        # Lab analytics show the lab/task titles and per-task means.
        return {Ns.LABS, Ns.LAB_ANALYTICS}
    if isinstance(obj, ERDiagramQuestion):
        return {Ns.ER_QUESTIONS}
    if isinstance(obj, Assessment):
        return {Ns.ASSESSMENTS, assessment_body_ns(obj.id)}
    if isinstance(obj, AssessmentItem):
        return {Ns.ASSESSMENTS, assessment_body_ns(obj.assessment_id)}
    return set()


def _after_flush(session: Session, flush_context) -> None:
    if not _cache_ready:
        # Table not provisioned yet -> skip; caching is simply inactive so far.
        return
    namespaces: set[str] = set()
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        namespaces |= _model_namespaces(obj)
    for ns in namespaces:
        # Same transaction as the mutation -> atomic; raw SQL, so it does not
        # re-enter the ORM unit of work (no recursion into after_flush).
        bump_version(session, ns)


_events_registered = False


def register_invalidation_events() -> None:
    """Install the after_flush auto-invalidation listener. Idempotent."""
    global _events_registered
    if _events_registered:
        return
    event.listen(SessionLocal, "after_flush", _after_flush)
    _events_registered = True


def bootstrap(engine) -> None:
    """
    Ensure the cache_versions table exists (idempotent, both backends) and seed the
    static namespaces, then mark the cache ready and install the invalidation event.
    Safe to call once at startup under concurrent workers (CREATE TABLE IF NOT
    EXISTS / INSERT-if-absent race harmlessly).
    """
    global _cache_ready
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS cache_versions ("
            "name VARCHAR(64) PRIMARY KEY, version BIGINT NOT NULL DEFAULT 0)"
        ))
        for ns in ALL_NAMESPACES:
            # Seed at 0 if absent; ON CONFLICT keeps it race-safe when two workers
            # bootstrap simultaneously. Portable across SQLite (3.24+) and PostgreSQL.
            conn.execute(
                text(
                    "INSERT INTO cache_versions (name, version) VALUES (:n, 0) "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {"n": ns},
            )
    _cache_ready = True
    register_invalidation_events()
