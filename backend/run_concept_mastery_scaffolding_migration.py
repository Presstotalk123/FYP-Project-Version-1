"""
Migration: Add concept_mastery.scaffolding_level (per-concept adaptive scaffolding).

Run once against your PostgreSQL (Supabase/Azure) database:
    python run_concept_mastery_scaffolding_migration.py

Idempotent: ADD COLUMN IF NOT EXISTS, so re-running is a no-op. Existing rows are
left NULL; scaffolding_engine seeds their level from mastery_level on read and
persists it on the student's next attempt, so no backfill is needed.
Local SQLite dev does not need this — app/main.py patches the column on startup.
"""
from sqlalchemy import create_engine, text
from app.config import settings


def run_migration():
    print(f"Connecting to: {settings.DATABASE_URL[:50]}...")
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        print("Adding 'scaffolding_level' to concept_mastery (if not exists)...")
        conn.execute(text(
            "ALTER TABLE concept_mastery ADD COLUMN IF NOT EXISTS scaffolding_level VARCHAR(20)"
        ))
        conn.commit()

    print("\n[OK] Migration complete!")
    print("  Column ensured: concept_mastery.scaffolding_level")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
