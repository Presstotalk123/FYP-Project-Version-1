"""Create or upgrade the Relational Algebra tables (ra_questions, ra_question_parts,
ra_attempts) on PostgreSQL by hand:
    python run_ra_tables_migration.py

Usually not needed: while RA_ENABLED is on, the backend does the same at startup
(app/services/ra/local_schema.py). This runs it regardless of RA_ENABLED.

Safe to re-run. It only adds: missing RA tables, missing RA columns, and one part for
each question saved before questions had parts. No other table is touched, and leaving
RA_ENABLED off afterwards leaves the app exactly as it was.
"""
from sqlalchemy import inspect as sa_inspect

from app.database import engine
from app.services.ra.local_schema import add_missing_columns

TABLES = ("ra_questions", "ra_question_parts", "ra_attempts")


def main() -> None:
    before = set(sa_inspect(engine).get_table_names())
    add_missing_columns(engine, force=True)
    after = set(sa_inspect(engine).get_table_names())
    for name in TABLES:
        state = "already existed" if name in before else ("created" if name in after else "MISSING (see the log)")
        print(f"{name}: {state}")


if __name__ == "__main__":
    main()
