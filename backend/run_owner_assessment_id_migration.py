"""Migration: add owner_assessment_id (content clone marker) and source_item_id.

Isolates per-assessment student progress by cloning content on publish. See
migrations/add_owner_assessment_id_columns.sql for details. Idempotent.
"""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import os
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings

# (table, column, column_def, index_name)  -- index_name None means no index.
MIGRATIONS = [
    ("questions", "owner_assessment_id", "INTEGER NULL", "ix_questions_owner_assessment_id"),
    ("labs", "owner_assessment_id", "INTEGER NULL", "ix_labs_owner_assessment_id"),
    ("lab_tasks", "owner_assessment_id", "INTEGER NULL", "ix_lab_tasks_owner_assessment_id"),
    ("er_diagram_questions", "owner_assessment_id", "INTEGER NULL", "ix_er_diagram_questions_owner_assessment_id"),
    ("assessment_items", "source_item_id", "INTEGER NULL", None),
]


def run_postgres():
    import psycopg2
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            for table, column, column_def, index_name in MIGRATIONS:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = %s AND column_name = %s
                    """,
                    (table, column),
                )
                if cur.fetchone():
                    print(f"[OK] Column '{column}' already exists in {table} table.")
                else:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def};")
                    print(f"[OK] Added '{column}' column to {table} table.")
                if index_name:
                    cur.execute(
                        f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({column});"
                    )
                    print(f"[OK] Ensured index '{index_name}' on {table}({column}).")
        conn.commit()
    finally:
        conn.close()


def run_sqlite():
    import sqlite3
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        for table, column, column_def, index_name in MIGRATIONS:
            cur = conn.execute(f"PRAGMA table_info({table})")
            existing_cols = [row[1] for row in cur.fetchall()]
            if column in existing_cols:
                print(f"[OK] Column '{column}' already exists in {table} table.")
            else:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}")
                print(f"[OK] Added '{column}' column to {table} table.")
            if index_name:
                conn.execute(
                    f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({column})"
                )
                print(f"[OK] Ensured index '{index_name}' on {table}({column}).")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Migration: add owner_assessment_id / source_item_id columns")
    print("=" * 60)
    if settings.DATABASE_URL.startswith("sqlite"):
        run_sqlite()
    else:
        run_postgres()
    print("Done.")
