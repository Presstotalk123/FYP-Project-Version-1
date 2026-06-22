"""
Run database migration for lab_tasks table
Usage: python run_migration.py
"""
import sqlite3
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent / "app.db"
MIGRATION_SQL = Path(__file__).parent / "migrations" / "add_lab_tasks.sql"

def run_migration():
    """Run the lab_tasks migration"""
    try:
        # Read migration SQL
        with open(MIGRATION_SQL, 'r') as f:
            migration_sql = f.read()

        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Execute migration
        cursor.executescript(migration_sql)
        conn.commit()

        # Verify table was created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='lab_tasks';")
        result = cursor.fetchone()

        if result:
            print("[OK] Migration successful!")
            print(f"[OK] Table 'lab_tasks' created")

            # Show table schema
            cursor.execute("PRAGMA table_info(lab_tasks);")
            columns = cursor.fetchall()
            print(f"[OK] Table has {len(columns)} columns:")
            for col in columns:
                print(f"  - {col[1]} ({col[2]})")
        else:
            print("[ERROR] Migration failed: table not created")

        conn.close()

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        raise

if __name__ == "__main__":
    run_migration()
