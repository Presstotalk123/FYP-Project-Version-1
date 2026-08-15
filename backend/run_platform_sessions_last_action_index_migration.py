"""
Migration: Add index platform_sessions.last_action_at (presence queries).

Run once against your PostgreSQL (Supabase/Azure) database:
    python run_platform_sessions_last_action_index_migration.py

The active-user count (count_online / list_online) filters sessions on
last_action_at against a recent cutoff. platform_sessions grows by one row per
login and is never pruned, so without this index that filter becomes a
full-table scan that degrades as the table grows.

Idempotent: CREATE INDEX IF NOT EXISTS, so re-running is a no-op.
Local SQLite dev does not need this — app/main.py creates the index on startup.

Note: a plain CREATE INDEX briefly blocks writes to the table for the duration
of the build. Run this while the table is small and it is effectively instant.
If you ever need to add it to a large, live table, switch to
    CREATE INDEX CONCURRENTLY ...
run OUTSIDE a transaction (autocommit), which builds without blocking writes.
"""
from sqlalchemy import create_engine, text
from app.config import settings


def run_migration():
    print(f"Connecting to: {settings.DATABASE_URL[:50]}...")
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        print("Creating index ix_platform_sessions_last_action_at (if not exists)...")
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_platform_sessions_last_action_at "
            "ON platform_sessions (last_action_at)"
        ))
        conn.commit()

    print("\n[OK] Migration complete!")
    print("  Index ensured: ix_platform_sessions_last_action_at on platform_sessions (last_action_at)")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
