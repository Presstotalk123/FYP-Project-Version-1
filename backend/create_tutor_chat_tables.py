"""Additive, non-destructive migration for the SQL-tutor chat persistence.

Creates ONLY the two new tables (`tutor_chat_conversations`, `tutor_chat_messages`)
on whatever database `settings.DATABASE_URL` points at. Uses ``checkfirst=True`` so
it is a no-op when the table already exists and NEVER drops or alters existing
tables/data — safe to run against the live Azure Postgres and safe to re-run.

Run:  cd backend && python create_tutor_chat_tables.py
"""
from sqlalchemy import inspect
from app.config import settings
from app.database import engine
from app.models.tutor_chat_conversation import TutorChatConversation
from app.models.tutor_chat_message import TutorChatMessage

# Conversations must exist before messages (FK target).
MODELS = (TutorChatConversation, TutorChatMessage)


def main() -> None:
    print(f"Connecting to: {settings.DATABASE_URL[:50]}...")
    inspector = inspect(engine)
    for model in MODELS:
        table = model.__table__
        existed = inspector.has_table(table.name)
        table.create(bind=engine, checkfirst=True)
        print(f"  {'already present' if existed else 'CREATED'}: {table.name}")

    # Verify
    print("\nVerifying...")
    inspector = inspect(engine)  # refresh
    for model in MODELS:
        name = model.__table__.name
        print(f"  {'[OK]' if inspector.has_table(name) else '[MISSING]'} {name}")
    print("\nDone. This script is safe to re-run.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
