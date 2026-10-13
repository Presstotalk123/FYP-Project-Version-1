"""One-off migration: add deductions_json to er_submissions.

The column holds the extra-element deductions taken off a graded attempt's
score, as the JSON list compute_grade put in score.deductions (see
services/erd_tutor/scoring.py); after a staff correction it holds the re-capped
list. NULL means the grader confirmed no extras, which is also how every attempt
graded before the column existed reads.

SQLite gets the column from the ALTER list in main.py at startup, so this is
only needed against Postgres, once, before deploying extra-element deductions:
    python run_er_submission_deductions_migration.py

Same shape as run_er_submission_regraded_at_migration.py, for the same reason:
the table already exists everywhere, and create_all never adds columns.

Safe to re-run: the column is added only when it is missing.
"""
from sqlalchemy import inspect as sa_inspect, text

from app.database import engine

TABLE = "er_submissions"
COLUMNS = {
    "deductions_json": "TEXT",
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
