"""
Migration: Add name and class_group columns to users table.
Run once against your PostgreSQL (Supabase) database.

Usage:
    python run_user_profile_migration.py
"""
from sqlalchemy import create_engine, text
from app.config import settings


def run_migration():
    print(f"Connecting to: {settings.DATABASE_URL[:50]}...")
    engine = create_engine(settings.DATABASE_URL)

    with engine.connect() as conn:
        print("Adding 'name' column to users table (if not exists)...")
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(255) DEFAULT NULL"
        ))

        print("Adding 'class_group' column to users table (if not exists)...")
        conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS class_group VARCHAR(100) DEFAULT NULL"
        ))

        print("Adding 'name' column to whitelist_entries table (if not exists)...")
        conn.execute(text(
            "ALTER TABLE whitelist_entries ADD COLUMN IF NOT EXISTS name VARCHAR(255) DEFAULT NULL"
        ))

        print("Adding 'class_group' column to whitelist_entries table (if not exists)...")
        conn.execute(text(
            "ALTER TABLE whitelist_entries ADD COLUMN IF NOT EXISTS class_group VARCHAR(100) DEFAULT NULL"
        ))

        conn.commit()


    print("\n✓ Migration complete!")
    print("  Columns added:  name (VARCHAR 255, nullable)")
    print("                  class_group (VARCHAR 100, nullable)")
    print("  Existing rows will have NULL for both new columns.")


if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
