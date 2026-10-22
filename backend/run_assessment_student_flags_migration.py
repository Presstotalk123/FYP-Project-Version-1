"""One-off migration: create the assessment_student_flags table on Postgres.

SQLite creates it at startup (main.py create_all), so this is only needed
against Postgres, once, before you deploy the staff flag on the assessment
student lists:

    python run_assessment_student_flags_migration.py

Safe to re-run: create_all only emits CREATE TABLE for a table that is
missing, and the unique constraint is part of that CREATE, so there is
nothing to repair afterwards. Mirrors run_user_preferences_migration.py.
"""
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.engine import Engine

from app.database import Base, engine
from app.models.assessment_student_flag import AssessmentStudentFlag


def ensure_schema(target_engine: Engine) -> str:
    """Create assessment_student_flags if missing. Returns what happened, so
    a deploy log distinguishes "just created" from "nothing to do"."""
    table_name = AssessmentStudentFlag.__table__.name
    if sa_inspect(target_engine).has_table(table_name):
        return f"{table_name} ready (table already present)"

    Base.metadata.create_all(
        bind=target_engine, tables=[AssessmentStudentFlag.__table__]
    )
    return f"{table_name} created"


def main() -> None:
    print(ensure_schema(engine))


if __name__ == "__main__":
    main()
