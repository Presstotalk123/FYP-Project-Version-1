"""Migration: add anti_cheat_enabled column to assessments table."""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import os
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings

NEW_COLUMNS = [
    ("anti_cheat_enabled", "INTEGER NOT NULL DEFAULT 1"),
]


def run_postgres():
    import psycopg2
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            for column_name, column_def in NEW_COLUMNS:
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'assessments' AND column_name = %s
                    """,
                    (column_name,),
                )
                if cur.fetchone():
                    print(f"[OK] Column '{column_name}' already exists in assessments table.")
                    continue
                cur.execute(f"ALTER TABLE assessments ADD COLUMN {column_name} {column_def};")
                print(f"[OK] Added '{column_name}' column to assessments table.")
        conn.commit()
    finally:
        conn.close()


def run_sqlite():
    import sqlite3
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("PRAGMA table_info(assessments)")
        existing_cols = [row[1] for row in cur.fetchall()]
        for column_name, column_def in NEW_COLUMNS:
            if column_name in existing_cols:
                print(f"[OK] Column '{column_name}' already exists in assessments table.")
                continue
            conn.execute(f"ALTER TABLE assessments ADD COLUMN {column_name} {column_def}")
            print(f"[OK] Added '{column_name}' column to assessments table.")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Assessments Column Migration: add anti_cheat_enabled column")
    print("=" * 60)
    if settings.DATABASE_URL.startswith("sqlite"):
        run_sqlite()
    else:
        run_postgres()
