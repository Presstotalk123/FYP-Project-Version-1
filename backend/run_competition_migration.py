"""Add only Database Rescue tables; never drop or reset application tables.

Run from backend: python run_competition_migration.py
Safe to repeat on both PostgreSQL and SQLite. Existing users must already exist.
Do NOT use the legacy destructive create_tables.py to upgrade a running database.
"""
from sqlalchemy import inspect
from app.database import Base, engine
from app.models import competition  # noqa: F401


def migrate(bind=engine):
    if not inspect(bind).has_table("users"):
        raise RuntimeError("Initialise the application users table before adding Competition tables.")
    tables = [t for t in Base.metadata.sorted_tables if t.name == "competitions" or t.name.startswith("competition_")]
    Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)
    return [t.name for t in tables]


if __name__ == "__main__":
    print("Competition tables ready: " + ", ".join(migrate()))
