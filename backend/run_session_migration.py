"""
Migration script to add unique constraint to lab_sessions table.
Handles edge cases and provides clear feedback.
"""
import sqlite3
import os
import sys

# Fix Unicode encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def run_migration():
    db_path = 'app.db'

    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found!")
        print(f"Current directory: {os.getcwd()}")
        print("Make sure you're in the backend directory.")
        sys.exit(1)

    print(f"Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Step 1: Check if migration already applied
        print("\n1. Checking if migration already applied...")
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='lab_sessions';")
        result = cursor.fetchone()

        if result and 'UNIQUE' in result[0] and 'lab_id, user_id, is_active' in result[0]:
            print("[OK] Migration already applied! Unique constraint exists.")
            print("\nCurrent table schema:")
            print(result[0])
            return

        print("[X] Unique constraint not found. Applying migration...")

        # Step 2: Drop temporary table if exists from previous failed attempt
        print("\n2. Cleaning up any previous migration attempts...")
        cursor.execute("DROP TABLE IF EXISTS lab_sessions_new;")

        # Step 3: Create new table with constraint
        print("\n3. Creating new table with unique constraint...")
        cursor.execute("""
            CREATE TABLE lab_sessions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lab_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                db_file_path VARCHAR(500) NOT NULL,
                is_active INTEGER DEFAULT 1,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                FOREIGN KEY (lab_id) REFERENCES labs(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE (lab_id, user_id, is_active)
            );
        """)
        print("[OK] New table created")

        # Step 4: Copy data
        print("\n4. Copying data from old table...")
        cursor.execute("SELECT COUNT(*) FROM lab_sessions;")
        old_count = cursor.fetchone()[0]
        print(f"   Found {old_count} existing sessions")

        cursor.execute("""
            INSERT OR IGNORE INTO lab_sessions_new
            SELECT id, lab_id, user_id, db_file_path, is_active, started_at, ended_at
            FROM lab_sessions;
        """)

        cursor.execute("SELECT COUNT(*) FROM lab_sessions_new;")
        new_count = cursor.fetchone()[0]
        print(f"[OK] Copied {new_count} sessions")

        if old_count != new_count:
            print(f"[!]  Warning: {old_count - new_count} duplicate sessions were skipped")

        # Step 5: Drop old table
        print("\n5. Dropping old table...")
        cursor.execute("DROP TABLE lab_sessions;")
        print("[OK] Old table dropped")

        # Step 6: Rename new table
        print("\n6. Renaming new table...")
        cursor.execute("ALTER TABLE lab_sessions_new RENAME TO lab_sessions;")
        print("[OK] Table renamed")

        # Step 7: Recreate indexes
        print("\n7. Creating indexes...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_lab_user ON lab_sessions(lab_id, user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_active_sessions ON lab_sessions(lab_id, is_active);")
        print("[OK] Indexes created")

        # Step 8: Commit changes
        conn.commit()
        print("\n[OK] Migration completed successfully!")

        # Step 9: Verify
        print("\n9. Verifying migration...")
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='lab_sessions';")
        result = cursor.fetchone()
        print("\nNew table schema:")
        print(result[0])

        if 'UNIQUE' in result[0]:
            print("\n[OK][OK][OK] UNIQUE constraint successfully added!")
        else:
            print("\n[X] ERROR: Constraint not found after migration!")

    except Exception as e:
        print(f"\n[X] Migration failed: {e}")
        conn.rollback()
        print("\nRolling back changes...")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    print("="*60)
    print("Lab Sessions Unique Constraint Migration")
    print("="*60)
    run_migration()
    print("\n" + "="*60)
    print("Done!")
    print("="*60)
