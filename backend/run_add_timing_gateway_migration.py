"""
Migration: Timing Gateway (per-class-group assessment access windows).
Run once against your PostgreSQL (Supabase/Azure) database.

Usage:
    python run_add_timing_gateway_migration.py

Adds:
  - assessments.gateway_enabled           (INTEGER NOT NULL DEFAULT 0)
  - assessment_sessions.hard_deadline     (TIMESTAMPTZ NULL)
  - assessment_class_windows              (new table, start_at/end_at TIMESTAMPTZ)

Idempotent: ADD COLUMN / CREATE TABLE / CREATE INDEX use IF NOT EXISTS, so re-running
is a no-op. Also corrects a bug in the original version of this migration, which created
hard_deadline/start_at/end_at as plain TIMESTAMP (no time zone) instead of TIMESTAMPTZ —
inconsistent with every other timing column (end_time, joined_at, submitted_at), all of
which are TIMESTAMPTZ. A "without time zone" column returns a *naive* Python datetime;
the API then serialized it with no UTC offset, and browsers parsed it as local time
instead of UTC, shifting the deadline by the viewer's UTC offset (e.g. 8 hours early in
Singapore) and causing spurious near-instant auto-submits. This version detects and
corrects any column already created with the wrong type, treating the existing naive
values as UTC (they always were UTC digits, just untagged) rather than shifting them.

Local SQLite dev does not need this — the columns are added on startup in app/main.py
and the table is created by Base.metadata.create_all() from the (correct) SQLAlchemy
models; SQLite has no real tz-aware column type either way.
"""
from sqlalchemy import create_engine, text
from app.config import settings


def _fix_column_type_if_naive(conn, table: str, column: str) -> None:
    """If `table.column` was created as TIMESTAMP (no time zone), convert it to
    TIMESTAMPTZ, reinterpreting the existing naive digits as UTC. No-op if already
    TIMESTAMPTZ."""
    data_type = conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {"table": table, "column": column}).scalar()

    if data_type == "timestamp without time zone":
        print(f"  Correcting {table}.{column}: TIMESTAMP -> TIMESTAMPTZ (as UTC)...")
        conn.execute(text(
            f'ALTER TABLE {table} ALTER COLUMN {column} '
            f"TYPE TIMESTAMPTZ USING {column} AT TIME ZONE 'UTC'"
        ))
    elif data_type is None:
        print(f"  {table}.{column} does not exist yet (will be created below).")
    else:
        print(f"  {table}.{column} already {data_type} — no correction needed.")


def run_migration():
    print(f"Connecting to: {settings.DATABASE_URL[:50]}...")
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        print("Adding assessments.gateway_enabled (if not exists)...")
        conn.execute(text(
            "ALTER TABLE assessments ADD COLUMN IF NOT EXISTS gateway_enabled INTEGER NOT NULL DEFAULT 0"
        ))

        print("Adding assessment_sessions.hard_deadline (if not exists)...")
        conn.execute(text(
            "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS hard_deadline TIMESTAMPTZ NULL"
        ))

        print("Creating 'assessment_class_windows' table (if not exists)...")
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS assessment_class_windows (
                id            SERIAL PRIMARY KEY,
                assessment_id INTEGER NOT NULL REFERENCES assessments(id),
                class_group   VARCHAR(100) NOT NULL,
                start_at      TIMESTAMPTZ NOT NULL,
                end_at        TIMESTAMPTZ NOT NULL,
                is_enabled    INTEGER NOT NULL DEFAULT 1,
                CONSTRAINT uq_assessment_class_window UNIQUE (assessment_id, class_group)
            )
            """
        ))

        print("Creating index on assessment_class_windows (if not exists)...")
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_assessment_class_windows_assessment "
            "ON assessment_class_windows (assessment_id, class_group)"
        ))

        conn.commit()

        print("\nChecking for the naive-timestamp bug on already-migrated databases...")
        _fix_column_type_if_naive(conn, "assessment_sessions", "hard_deadline")
        _fix_column_type_if_naive(conn, "assessment_class_windows", "start_at")
        _fix_column_type_if_naive(conn, "assessment_class_windows", "end_at")
        conn.commit()

    print("\n[OK] Migration complete!")
    print("  Columns: assessments.gateway_enabled, assessment_sessions.hard_deadline (TIMESTAMPTZ)")
    print("  Table:   assessment_class_windows (start_at/end_at TIMESTAMPTZ, unique on assessment_id, class_group)")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
