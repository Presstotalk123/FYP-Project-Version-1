"""Create the course_info table.

Uses SQLAlchemy ``create_all`` on the CourseInfo model so the DDL is generated
for whatever dialect ``DATABASE_URL`` points at (SQLite locally, PostgreSQL /
Azure in production). ``create_all`` only creates tables that do not already
exist, so this is idempotent and never touches existing tables or data.
``migrations/add_course_info_table.sql`` documents the equivalent PostgreSQL DDL
for reference.
"""
from sqlalchemy import create_engine

from app.config import settings
from app.database import Base
from app.models.course_info import CourseInfo


def main():
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine, tables=[CourseInfo.__table__])
    print("course_info migration applied to", settings.DATABASE_URL)


if __name__ == "__main__":
    main()
