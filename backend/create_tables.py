"""
One-time script to create database tables in Supabase PostgreSQL.
Run this once after setting up the database.
"""
from sqlalchemy import create_engine, text
from app.config import settings
from app.database import Base

# Import all models to register them
from app.models.user import User
from app.models.whitelist import WhitelistEntry
from app.models.question import Question
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.attempt import Attempt
from app.models.progress import UserProgress
from app.models.lab import Lab
from app.models.lab_session import LabSession
from app.models.lab_attempt import LabAttempt
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.models.assessment_item_visit import AssessmentItemVisit
from app.models.er_lab import ErLab
from app.models.er_lab_question import ErLabQuestion
from app.models.er_lab_session import ErLabSession
from app.models.er_lab_submission import ErLabSubmission

def create_tables():
    print(f"Connecting to: {settings.DATABASE_URL[:50]}...")

    engine = create_engine(settings.DATABASE_URL)

    # First, drop all existing tables and indexes to start fresh
    print("\nDropping existing tables and indexes...")
    with engine.connect() as conn:
        # Drop all indexes first
        print("Dropping indexes...")
        indexes = [
            'idx_user_lab', 'idx_user_lab_attempts', 'idx_user_lab_submissions',
            'idx_task_user', 'idx_task_submitted', 'idx_session_submitted',
            'idx_lab_user', 'idx_active_sessions', 'idx_lab_order', 'idx_lab_created',
            'ix_assessment_sessions_user_assessment', 'ix_aiv_session_item',
            'ix_er_lab_questions_lab_order', 'ix_er_lab_questions_lab_deleted',
            'ix_er_lab_sessions_lab_user', 'ix_er_lab_sessions_lab_active',
            'uq_active_er_session_per_user_lab',
            'ix_er_lab_submissions_question_user', 'ix_er_lab_submissions_user_lab',
            'ix_er_lab_submissions_question_time',
        ]
        for idx in indexes:
            try:
                conn.execute(text(f"DROP INDEX IF EXISTS {idx} CASCADE"))
                print(f"  Dropped index: {idx}")
            except Exception as e:
                print(f"  Could not drop {idx}: {e}")

        conn.commit()

        # Drop all tables
        print("\nDropping tables...")
        tables = [
            'assessment_item_visits', 'er_lab_submissions',
            'assessment_sessions', 'assessment_items', 'assessments',
            'er_lab_sessions', 'er_lab_questions', 'er_labs',
            'whitelist_entries',
            'lab_task_submissions', 'lab_tasks', 'lab_attempts',
            'lab_sessions', 'user_progress', 'attempts',
            'labs', 'er_diagram_questions', 'questions', 'users',
        ]
        for table in tables:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
                print(f"  Dropped table: {table}")
            except Exception as e:
                print(f"  Could not drop {table}: {e}")

        conn.commit()

    print("\n" + "="*50)
    print("Creating fresh tables...")
    print("="*50 + "\n")

    # Create all tables
    Base.metadata.create_all(bind=engine)

    print("✓ All tables created successfully!\n")

    # Verify tables were created
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]

        print(f"Tables created ({len(tables)} total):")
        for table in tables:
            print(f"  ✓ {table}")

    print("\n✓ Migration complete! You can now start your FastAPI app.")
    print("  Run: python -m uvicorn app.main:app --reload")

if __name__ == "__main__":
    try:
        create_tables()
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
