"""One-off migration: add added_by_staff_id / added_reason to er_submissions.

These two columns mark a submission a staff member created on a student's behalf,
from a diagram the student never submitted (see app/models/er_submission.py).

SQLite gets them from the ALTER list in main.py at startup, so this is only needed
against Postgres, once, before deploying staff-added submissions:
    python run_er_submission_added_by_migration.py

Why ALTER and not create_all: the table already exists in every environment, and
create_all only ever emits CREATE TABLE — against an existing table it does nothing
at all, silently. That is the same trap run_er_drafts_migration.py documents for its
unique constraint.

Safe to re-run: each column is added only when it is missing.
"""
from sqlalchemy import inspect as sa_inspect, text

from app.database import engine

TABLE = "er_submissions"

# Deliberately no FOREIGN KEY clause. The ORM model declares the relationship for
# query construction; adding the constraint to a live table takes a lock and buys
# nothing here, because the only writer is our own service.
COLUMNS = {
    "added_by_staff_id": "INTEGER",
    "added_reason": "TEXT",
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

    print(f"{TABLE} ready. added: {added or 'nothing, both columns already present'}")


if __name__ == "__main__":
    main()
