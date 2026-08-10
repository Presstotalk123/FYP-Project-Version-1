"""One-off migration: create query_reviews (and its indexes) on Postgres.

SQLite creates the table automatically at startup (main.py create_all); on
Postgres (Supabase) create_all is not run, so run this once before/after
deploying the student-analytics feature:

    python run_query_reviews_migration.py

Non-destructive: create_all with an explicit `tables=` list only creates that one
table (skipped if it already exists) and never touches any other table's data.
"""
from app.database import Base, engine
from app.models.query_review import QueryReview


def main() -> None:
    Base.metadata.create_all(bind=engine, tables=[QueryReview.__table__])
    # create_all skips an existing table entirely, so create indexes explicitly
    # (idempotent via checkfirst) in case the table already shipped without them.
    for index in QueryReview.__table__.indexes:
        index.create(bind=engine, checkfirst=True)
    print("query_reviews ready (table + indexes)")


if __name__ == "__main__":
    main()
