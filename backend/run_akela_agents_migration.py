"""Create the Akela multi-agent / learning-analytics tables.

Uses SQLAlchemy ``create_all`` on the new ORM models so the DDL is generated for
whatever dialect ``DATABASE_URL`` points at (SQLite locally, PostgreSQL / Supabase
in production). ``main.py`` auto-creates these for SQLite on startup; PostgreSQL
needs this script run once, before flipping ``AKELA_AGENTS_ENABLED`` /
``SQL_TUTOR_ADAPTIVE`` on.

Optionally seeds the concept taxonomy afterwards (``--seed``).
"""
import sys

from sqlalchemy import create_engine

from app.config import settings
from app.database import Base
from app.models.sql_concept import SqlConcept
from app.models.sql_concept_prerequisite import SqlConceptPrerequisite
from app.models.question_concept import QuestionConcept
from app.models.learning_event import LearningEvent
from app.models.concept_mastery import ConceptMastery
from app.models.solo_classification import SoloClassification
from app.models.sql_tutor_conversation import SqlTutorConversation
from app.models.sql_tutor_message import SqlTutorMessage

TABLES = [
    SqlConcept.__table__,
    SqlConceptPrerequisite.__table__,
    QuestionConcept.__table__,
    LearningEvent.__table__,
    ConceptMastery.__table__,
    SoloClassification.__table__,
    SqlTutorConversation.__table__,
    SqlTutorMessage.__table__,
]


def main():
    engine = create_engine(settings.DATABASE_URL)
    Base.metadata.create_all(engine, tables=TABLES)
    print("akela_agents migration applied to", settings.DATABASE_URL[:40])

    if "--seed" in sys.argv:
        from app.services.concept_taxonomy_seed import seed_taxonomy
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            created = seed_taxonomy(db)
            print(f"seeded concept taxonomy ({created} concepts ensured)")
        finally:
            db.close()


if __name__ == "__main__":
    main()
