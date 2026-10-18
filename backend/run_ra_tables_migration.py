"""Create the Relational Algebra tables (ra_questions, ra_attempts) on PostgreSQL.

SQLite creates them automatically at startup (main.py create_all), so this is only
needed against Postgres, once, before switching RA_ENABLED on there:
    python run_ra_tables_migration.py

Safe to re-run: create_all only creates tables that are missing. The tables are new and
nothing else references them, so running this changes no existing table, and leaving
RA_ENABLED off afterwards leaves the app exactly as it was.
"""
from sqlalchemy import inspect as sa_inspect

from app.database import Base, engine
from app.models.ra_attempt import RAAttempt
from app.models.ra_question import RAQuestion

TABLES = [RAQuestion.__table__, RAAttempt.__table__]


def main() -> None:
    before = set(sa_inspect(engine).get_table_names())
    Base.metadata.create_all(bind=engine, tables=TABLES)
    for table in TABLES:
        state = "already existed" if table.name in before else "created"
        print(f"{table.name}: {state}")


if __name__ == "__main__":
    main()
