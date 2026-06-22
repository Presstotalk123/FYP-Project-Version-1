"""Migration: add template_db_path column to labs table if missing."""
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import os
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings


def run_postgres():
    import psycopg2
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'labs' AND column_name = 'template_db_path'
            """)
            if cur.fetchone():
                print("[OK] Column 'template_db_path' already exists in labs table.")
                return
            cur.execute(
                "ALTER TABLE labs ADD COLUMN template_db_path VARCHAR(500) NOT NULL DEFAULT '';"
            )
        conn.commit()
        print("[OK] Added 'template_db_path' column to labs table.")
    finally:
        conn.close()


def run_sqlite():
    import sqlite3
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("PRAGMA table_info(labs)")
        cols = [row[1] for row in cur.fetchall()]
        if "template_db_path" in cols:
            print("[OK] Column 'template_db_path' already exists in labs table.")
            return
        conn.execute("ALTER TABLE labs ADD COLUMN template_db_path VARCHAR(500) NOT NULL DEFAULT ''")
        conn.commit()
        print("[OK] Added 'template_db_path' column to labs table.")
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Labs Column Migration: add template_db_path")
    print("=" * 60)
    if settings.DATABASE_URL.startswith("sqlite"):
        run_sqlite()
    else:
        run_postgres()
