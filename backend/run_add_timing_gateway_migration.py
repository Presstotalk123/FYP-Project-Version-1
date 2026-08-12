"""
Migration: Timing Gateway (per-class-group assessment access windows).
Run once against your PostgreSQL (Supabase/Azure) database.

Usage:
    python run_add_timing_gateway_migration.py

Adds:
  - assessments.gateway_enabled           (INTEGER NOT NULL DEFAULT 0)
  - assessment_sessions.hard_deadline     (TIMESTAMP NULL)
  - assessment_class_windows              (new table)

Idempotent: ADD COLUMN / CREATE TABLE / CREATE INDEX use IF NOT EXISTS, so re-running
is a no-op. Local SQLite dev does not need this — the columns are added on startup in
app/main.py and the table is created by Base.metadata.create_all().
"""
from sqlalchemy import create_engine, text
from app.config import settings


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
            "ALTER TABLE assessment_sessions ADD COLUMN IF NOT EXISTS hard_deadline TIMESTAMP NULL"
        ))

        print("Creating 'assessment_class_windows' table (if not exists)...")
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS assessment_class_windows (
                id            SERIAL PRIMARY KEY,
                assessment_id INTEGER NOT NULL REFERENCES assessments(id),
                class_group   VARCHAR(100) NOT NULL,
                start_at      TIMESTAMP NOT NULL,
                end_at        TIMESTAMP NOT NULL,
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

    print("\n[OK] Migration complete!")
    print("  Columns: assessments.gateway_enabled, assessment_sessions.hard_deadline")
    print("  Table:   assessment_class_windows (unique on assessment_id, class_group)")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
