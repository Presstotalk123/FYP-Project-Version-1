"""
Migration: Add platform_sessions.left_at (active-user count).

Run once against your PostgreSQL (Supabase/Azure) database:
    python run_platform_sessions_left_at_migration.py

Idempotent: ADD COLUMN IF NOT EXISTS, so re-running is a no-op.
Local SQLite dev does not need this — app/main.py patches the column on startup.
"""
from sqlalchemy import create_engine, text
from app.config import settings


def run_migration():
    print(f"Connecting to: {settings.DATABASE_URL[:50]}...")
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        print("Adding 'left_at' to platform_sessions (if not exists)...")
        conn.execute(text(
            "ALTER TABLE platform_sessions ADD COLUMN IF NOT EXISTS left_at TIMESTAMPTZ"
        ))
        conn.commit()

    print("\n[OK] Migration complete!")
    print("  Column ensured: platform_sessions.left_at")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
