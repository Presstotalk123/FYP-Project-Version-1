"""One-off migration: add regraded_at to er_submissions.

The column marks when a rubric regrade (services/er_regrade.py) last replaced
the row's stored grade; the journey and the attempt view badge on it. NULL
means the grade is still the one produced at submit time or by an override.

SQLite gets the column from the ALTER list in main.py at startup, so this is
only needed against Postgres, once, before deploying the regrade badge:
    python run_er_submission_regraded_at_migration.py

Same shape as run_er_submission_added_by_migration.py, for the same reason:
the table already exists everywhere, and create_all never adds columns.

Safe to re-run: the column is added only when it is missing.
"""
from sqlalchemy import inspect as sa_inspect, text

from app.database import engine

TABLE = "er_submissions"
COLUMNS = {
    "regraded_at": "TIMESTAMP",
}


def main() -> None:
    inspector = sa_inspect(engine)
    if TABLE not in inspector.get_table_names():
        print(f"{TABLE} does not exist. Run run_er_submissions_migration.py first.")
        return

    existing = {column["name"] for column in inspector.get_columns(TABLE)}
    added = []
    with engine.connect() as conn:
        for name, sql_type in COLUMNS.items():
            if name in existing:
                continue
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN {name} {sql_type}"))
            added.append(name)
        conn.commit()

    print(f"{TABLE} ready. added: {added or 'nothing, column already present'}")


if __name__ == "__main__":
    main()
