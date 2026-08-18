"""One-off migration: create the user_preferences table on Postgres.

SQLite creates it automatically at startup (main.py create_all), so this is
only needed against Postgres, once, before deploying the server-side
"don't remind me again" for the ER-diagram guide:

    python run_user_preferences_migration.py

Safe to re-run: create_all only ever emits CREATE TABLE for a table that is
missing, and the table's only constraint (the composite primary key) is baked
into that CREATE, so there is nothing to repair afterwards. Mirrors
run_er_drafts_migration.py.
"""
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Engine

from app.database import Base, engine
from app.models.user_preference import UserPreference


def ensure_schema(target_engine: Engine) -> str:
    """Create user_preferences if missing. Returns what actually happened, so
    a deploy log distinguishes "just created" from "nothing to do"."""
    table_name = UserPreference.__table__.name
    if sa_inspect(target_engine).has_table(table_name):
        return "user_preferences ready (table already present)"

    Base.metadata.create_all(bind=target_engine, tables=[UserPreference.__table__])
    return "user_preferences created"


def main() -> None:
    print(ensure_schema(engine))


if __name__ == "__main__":
    main()
