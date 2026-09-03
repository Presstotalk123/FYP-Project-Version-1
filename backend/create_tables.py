"""
One-time script to create database tables in Supabase PostgreSQL.
Run this once after setting up the database.
"""
from sqlalchemy import create_engine, text
from app.config import settings
from app.database import Base

# Import all models to register them.
# Kept in sync with everything under app/models/ (not just what main.py registers
# for SQLite auto-create) — this script is the only path that provisions the
# full current schema on a fresh PostgreSQL database. See main.py's comment on
# why Postgres tables are pre-created here rather than via startup create_all.
from app.models.app_setting import AppSetting
from app.models.assessment import Assessment
from app.models.assessment_analytics import AssessmentAnalytics
from app.models.assessment_class_window import AssessmentClassWindow
from app.models.assessment_item import AssessmentItem
from app.models.assessment_item_visit import AssessmentItemVisit
from app.models.assessment_session import AssessmentSession
from app.models.attempt import Attempt
from app.models.concept_mastery import ConceptMastery
from app.models.course_info import CourseInfo
from app.models.er_diagram_draft import ErDiagramDraft
from app.models.er_diagram_image_draft import ErDiagramImageDraft
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.er_submission import ErSubmission
from app.models.erd_prompt_version import ErdPromptVersion
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.erd_tutor_message import ErdTutorMessage
from app.models.lab import Lab
from app.models.lab_attempt import LabAttempt
from app.models.lab_session import LabSession
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.learning_event import LearningEvent
from app.models.login_activity import LoginActivity
from app.models.platform_session import PlatformSession
from app.models.progress import UserProgress
from app.models.query_review import QueryReview
from app.models.question import Question
from app.models.question_concept import QuestionConcept
from app.models.solo_classification import SoloClassification
from app.models.sql_concept import SqlConcept
from app.models.sql_concept_prerequisite import SqlConceptPrerequisite
from app.models.sql_tutor_conversation import SqlTutorConversation
from app.models.sql_tutor_message import SqlTutorMessage
from app.models.tutor_chat_conversation import TutorChatConversation
from app.models.tutor_chat_message import TutorChatMessage
from app.models.user import User
from app.models.user_preference import UserPreference
from app.models.whitelist import WhitelistEntry
from app.core.cache import CacheVersion  # register cache_versions on Base

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
            'ix_erd_tutor_conv_lab', 'ix_erd_tutor_conv_standalone', 'ix_erd_tutor_msg_conv',
            'ix_tutor_chat_conv_lookup', 'ix_tutor_chat_msg_conv',
            'ix_query_review_question', 'ix_query_review_lab',
            'ix_erd_prompt_key_active',
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
            'query_reviews',
            'tutor_chat_messages', 'tutor_chat_conversations',
            'erd_tutor_messages', 'erd_tutor_conversations', 'erd_prompt_versions',
            'course_info',
            'assessment_item_visits', 'er_lab_submissions',
            'assessment_class_windows',
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
