"""Migration: create ER lab tables + partial unique active-session index."""
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import settings

SQL_FILE = os.path.join(os.path.dirname(__file__), "migrations", "add_er_lab_tables.sql")


def _split_statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def _is_sqlite() -> bool:
    return settings.DATABASE_URL.startswith("sqlite")


def run_sqlite():
    import sqlite3
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        print(f"Database file '{db_path}' not found.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    try:
        with open(SQL_FILE, "r", encoding="utf-8") as f:
            sql = f.read()
        for stmt in _split_statements(sql):
            conn.execute(stmt)

        # Partial unique active-session index (SQLite supports it).
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_er_session_per_user_lab "
            "ON er_lab_sessions(er_lab_id, user_id) WHERE is_active = 1;"
        )
        conn.commit()
        print("[OK] ER lab tables + indexes created (sqlite).")
    finally:
        conn.close()


def run_postgres():
    import psycopg2
    conn = psycopg2.connect(settings.DATABASE_URL)
    try:
        with conn.cursor() as cur:
            with open(SQL_FILE, "r", encoding="utf-8") as f:
                sql = f.read()
            for stmt in _split_statements(sql):
                cur.execute(stmt)
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_er_session_per_user_lab "
                "ON er_lab_sessions(er_lab_id, user_id) WHERE is_active = 1;"
            )
        conn.commit()
        print("[OK] ER lab tables + indexes created (postgres).")
    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("ER Lab Tables Migration")
    print("=" * 60)
    if _is_sqlite():
        run_sqlite()
    else:
        run_postgres()
