"""One-off migration: create er_submissions (and its indexes) on Postgres.

SQLite creates the table automatically at startup (main.py create_all); running
this locally is only needed to add the composite indexes to a table that already
existed before they were introduced.

Run once against Postgres before deploying the analytics feature:
    python run_er_submissions_migration.py

Postgres note (deliberate, deferred): checks_json is TEXT for SQLite parity. If
check-rate aggregation ever needs to move into SQL at scale, migrate the column
to JSONB on Postgres — the Python code is agnostic to the change.
"""
from app.database import Base, engine
from app.models.er_submission import ErSubmission


def main() -> None:
    Base.metadata.create_all(bind=engine, tables=[ErSubmission.__table__])
    # create_all skips existing tables entirely, so indexes added after the
    # table first shipped need explicit creation (idempotent via checkfirst).
    for index in ErSubmission.__table__.indexes:
        index.create(bind=engine, checkfirst=True)
    print("er_submissions ready (table + indexes)")


if __name__ == "__main__":
    main()
