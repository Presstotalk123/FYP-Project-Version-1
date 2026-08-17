"""Migration: add weighted_score column to assessment_sessions.

Persists the per-student weighted score at finalization so readers no longer
recompute it live. See migrations/add_assessment_session_weighted_score_column.sql
for details. Idempotent. Run backfill_assessment_session_weighted_scores.py afterwards
to populate the column for sessions finalized before this shipped.
"""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import os
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings

TABLE = "assessment_sessions"
NEW_COLUMNS = [
    ("weighted_score", "DOUBLE PRECISION"),
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
                    WHERE table_name = %s AND column_name = %s
                    """,
                    (TABLE, column_name),
                )
                if cur.fetchone():
                    print(f"[OK] Column '{column_name}' already exists in {TABLE} table.")
                    continue
                cur.execute(f"ALTER TABLE {TABLE} ADD COLUMN {column_name} {column_def};")
                print(f"[OK] Added '{column_name}' column to {TABLE} table.")
        conn.commit()
    finally:
        conn.close()


def run_sqlite():
    import sqlite3
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(f"PRAGMA table_info({TABLE})")
        existing_cols = [row[1] for row in cur.fetchall()]
        for column_name, _column_def in NEW_COLUMNS:
            if column_name in existing_cols:
                print(f"[OK] Column '{column_name}' already exists in {TABLE} table.")
                continue
            # SQLite affinity: DOUBLE PRECISION maps to REAL.
            conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN {column_name} REAL")
            print(f"[OK] Added '{column_name}' column to {TABLE} table.")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Migration: add weighted_score column to assessment_sessions")
    print("=" * 60)
    if settings.DATABASE_URL.startswith("sqlite"):
        run_sqlite()
    else:
        run_postgres()
    print("Done.")
