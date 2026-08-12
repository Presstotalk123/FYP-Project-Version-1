"""
Migration: Add the login_activities table (student login-streak / activity calendar).
Run once against your PostgreSQL (Supabase/Azure) database.

Usage:
    python run_login_activities_migration.py

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
        print("Creating 'login_activities' table (if not exists)...")
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS login_activities (
                id          SERIAL PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                login_date  DATE NOT NULL,
                created_at  TIMESTAMPTZ DEFAULT now(),
                CONSTRAINT _user_login_date_uc UNIQUE (user_id, login_date)
            )
            """
        ))

        print("Creating index on login_activities.user_id (if not exists)...")
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_login_activities_user_id ON login_activities (user_id)"
        ))

        conn.commit()

    print("\n[OK] Migration complete!")
    print("  Table created: login_activities (id, user_id, login_date, created_at)")
    print("  Unique constraint: (user_id, login_date)")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
