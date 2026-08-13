"""
Migration: Add the assessment_analytics table (materialized cohort/class-group averages).
Run once against your PostgreSQL (Supabase/Azure) database.

Usage:
    python run_assessment_analytics_migration.py

Idempotent: the CREATE TABLE / INDEX use IF NOT EXISTS, so re-running is a no-op.
Local SQLite dev does not need this — Base.metadata.create_all() creates the table
on startup.
"""
from sqlalchemy import create_engine, text
from app.config import settings


def run_migration():
    print(f"Connecting to: {settings.DATABASE_URL[:50]}...")
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        print("Creating 'assessment_analytics' table (if not exists)...")
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS assessment_analytics (
                id                  SERIAL PRIMARY KEY,
                assessment_id       INTEGER NOT NULL REFERENCES assessments(id),
                class_group         VARCHAR(255),
                student_count       INTEGER NOT NULL DEFAULT 0,
                avg_weighted_score  DOUBLE PRECISION,
                payload             TEXT NOT NULL,
                version             BIGINT NOT NULL DEFAULT 0,
                computed_at         TIMESTAMPTZ DEFAULT now()
            )
            """
        ))

        print("Creating indexes on assessment_analytics (if not exist)...")
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_assessment_analytics_scope "
            "ON assessment_analytics (assessment_id, class_group) "
            "WHERE class_group IS NOT NULL"
        ))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_assessment_analytics_cohort "
            "ON assessment_analytics (assessment_id) "
            "WHERE class_group IS NULL"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_assessment_analytics_assessment "
            "ON assessment_analytics (assessment_id)"
        ))

        conn.commit()

    print("\n[OK] Migration complete!")
    print("  Table created: assessment_analytics "
          "(id, assessment_id, class_group, student_count, avg_weighted_score, "
          "payload, version, computed_at)")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
