"""Create the ERD-tutor conversation tables.

Uses SQLAlchemy ``create_all`` on the two ORM models so the DDL is generated
for whatever dialect ``DATABASE_URL`` points at (SQLite locally, PostgreSQL /
Supabase in production). ``migrations/add_erd_tutor_tables.sql`` documents the
equivalent PostgreSQL DDL for reference.
"""
from sqlalchemy import create_engine

from app.config import settings
from app.database import Base
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.erd_tutor_message import ErdTutorMessage
from app.models.erd_prompt_version import ErdPromptVersion


def main():
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(
        engine,
        tables=[ErdTutorConversation.__table__, ErdTutorMessage.__table__, ErdPromptVersion.__table__],
    )
    print("erd_tutor migration applied to", settings.DATABASE_URL)


if __name__ == "__main__":
    main()
