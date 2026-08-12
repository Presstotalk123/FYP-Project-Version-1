"""
Migration: Add the platform_sessions table (student platform-time tracking).
Run once against your PostgreSQL (Supabase/Azure) database.

Usage:
    python run_platform_sessions_migration.py

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
        print("Creating 'platform_sessions' table (if not exists)...")
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS platform_sessions (
                id              SERIAL PRIMARY KEY,
                user_id         INTEGER NOT NULL REFERENCES users(id),
                login_date      DATE NOT NULL,
                login_at        TIMESTAMPTZ NOT NULL,
                last_action_at  TIMESTAMPTZ NOT NULL,
                created_at      TIMESTAMPTZ DEFAULT now()
            )
            """
        ))

        print("Creating indexes on platform_sessions (if not exist)...")
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_platform_sessions_user_id ON platform_sessions (user_id)"
        ))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_platform_sessions_user_date ON platform_sessions (user_id, login_date)"
        ))

        conn.commit()

    print("\n[OK] Migration complete!")
    print("  Table created: platform_sessions (id, user_id, login_date, login_at, last_action_at, created_at)")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
