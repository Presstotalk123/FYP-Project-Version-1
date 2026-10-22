"""Bring the RA tables up to date at startup: new tables, new columns, and data moves.

create_all only creates missing tables, never missing columns, and on PostgreSQL main.py
doesn't run it at all (several gunicorn workers would race). So RA does its own, small,
additive upgrade here, called once from main.py:

  * SQLite (local): add the columns, then move old rows forward.
  * PostgreSQL: only while RA_ENABLED is on (so a server without RA is never touched),
    and under an advisory lock so only one worker runs it at a time. Creates the RA
    tables if missing, adds the columns, moves old rows forward.

Everything is idempotent, so it simply does nothing once the database is current.
Moving old rows forward: a question saved before questions had parts gets one part made
from its own model answer, and its attempts are linked to that part.
"""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from app.config import settings

logger = logging.getLogger(__name__)

# (table, column, SQL type and default) — added when missing.
_COLUMNS = (
    ("ra_questions", "assessment_step_direction", "INTEGER NOT NULL DEFAULT 0"),
    ("ra_attempts", "part_id", "INTEGER REFERENCES ra_question_parts(id)"),
)
_LOCK_KEY = 727_001          # pg_advisory_lock key, private to this upgrade


def _tables():
    from app.models.ra_attempt import RAAttempt
    from app.models.ra_question import RAQuestion
    from app.models.ra_question_part import RAQuestionPart
    return [RAQuestion.__table__, RAQuestionPart.__table__, RAAttempt.__table__]


def _add_columns(conn: Connection) -> None:
    postgres = conn.dialect.name == "postgresql"
    for table, column, decl in _COLUMNS:
        if postgres:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {decl}"))
            continue
        existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        if column not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))


def _give_old_questions_a_part(conn: Connection) -> int:
    from app.models.ra_question_part import RAQuestionPart

    rows = conn.execute(text(
        "SELECT id, model_answer, checkpoints_json, suite_json, suite_summary_json FROM ra_questions q "
        "WHERE NOT EXISTS (SELECT 1 FROM ra_question_parts p WHERE p.question_id = q.id)")).fetchall()
    for qid, model_answer, checkpoints_json, suite_json, suite_summary_json in rows:
        result = conn.execute(RAQuestionPart.__table__.insert().values(
            question_id=qid, position=0, label="", description="", marks=1, model_answer=model_answer or "",
            checkpoints_json=checkpoints_json, suite_json=suite_json, suite_summary_json=suite_summary_json,
            is_deleted=0))
        conn.execute(text("UPDATE ra_attempts SET part_id = :pid WHERE question_id = :qid AND part_id IS NULL"),
                     {"pid": result.inserted_primary_key[0], "qid": qid})
    return len(rows)


def upgrade(conn: Connection) -> int:
    """Create/upgrade the RA tables on this connection; returns how many old questions
    were given a part. The caller commits."""
    from app.database import Base
    Base.metadata.create_all(bind=conn, tables=_tables())
    _add_columns(conn)
    return _give_old_questions_a_part(conn)


def add_missing_columns(engine: Engine, *, force: bool = False) -> None:
    """Called once at startup (main.py). ``force`` runs it on PostgreSQL even with RA off
    (run_ra_tables_migration.py)."""
    dialect = engine.dialect.name
    if dialect == "postgresql" and not (settings.RA_ENABLED or force):
        return
    if dialect not in ("sqlite", "postgresql"):
        return
    try:
        with engine.connect() as conn:
            if dialect == "postgresql":
                conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _LOCK_KEY})
            try:
                moved = upgrade(conn)
                conn.commit()
            finally:
                if dialect == "postgresql":
                    conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
                    conn.commit()
        if moved:
            logger.info("RA: gave %d existing question(s) a part", moved)
    except Exception:
        # Never stop the app from starting; RA pages will show the error instead.
        logger.exception("RA: could not upgrade the RA tables")
