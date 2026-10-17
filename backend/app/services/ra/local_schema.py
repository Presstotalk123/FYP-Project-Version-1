"""Columns added to the RA tables after they were first created, for local SQLite.

create_all only creates missing tables, never missing columns, so a local database whose
RA tables were created by an earlier commit needs them added. Same idea as the column
list in main.py, kept here so RA never edits that shared list. On PostgreSQL the RA tables
are created complete by run_ra_tables_migration.py, so nothing runs there.
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

_COLUMNS = (
    "ALTER TABLE ra_questions ADD COLUMN assessment_step_direction INTEGER NOT NULL DEFAULT 0",
)


def add_missing_columns(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    for stmt in _COLUMNS:
        with engine.connect() as conn:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass  # column already exists
