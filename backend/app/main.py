from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.config import settings
from app.database import engine, Base
from app.api.v1.endpoints import auth, questions, execute, attempts, chatbot, er_diagram, labs, er_labs, users, whitelist, assessments, student_assessments
# Import models to register them with SQLAlchemy
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

# Drop the broken non-partial unique index if it exists so create_all recreates it
# correctly as a partial index (WHERE is_active = 1). This fixes SQLite ignoring
# postgresql_where, which caused IntegrityError when creating a second session.
with engine.connect() as _conn:
    _conn.execute(text("DROP INDEX IF EXISTS uq_active_session_per_user_lab"))
    _conn.commit()

# Auto-create tables on startup for SQLite (local dev) only.
# For PostgreSQL, tables must be pre-created via create_tables.py to avoid
# a race condition where multiple gunicorn workers simultaneously try to create
# the same table and its implicit composite type, causing UniqueViolation.
if "sqlite" in settings.DATABASE_URL:
    Base.metadata.create_all(bind=engine)

# Add lab_type column if it doesn't exist (handles existing local SQLite databases)
with engine.connect() as _conn:
    try:
        _conn.execute(text("ALTER TABLE labs ADD COLUMN lab_type VARCHAR(10) NOT NULL DEFAULT 'sql'"))
        _conn.commit()
    except Exception:
        pass  # Column already exists

# Add password column to assessments if it doesn't exist
with engine.connect() as _conn:
    try:
        _conn.execute(text("ALTER TABLE assessments ADD COLUMN password VARCHAR(255)"))
        _conn.commit()
    except Exception:
        pass  # Column already exists

print(f"Connected to database: {settings.DATABASE_URL[:30]}...")

# Create FastAPI application
app = FastAPI(
    title="SQL Learning Platform API",
    description="Backend API for SQL learning and practice platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(questions.router, prefix="/api/v1")
app.include_router(execute.router, prefix="/api/v1")
app.include_router(attempts.router, prefix="/api/v1")
app.include_router(chatbot.router, prefix="/api/v1")
app.include_router(er_diagram.router, prefix="/api/v1")
app.include_router(labs.router, prefix="/api/v1")
app.include_router(er_labs.router, prefix="/api/v1")
app.include_router(er_labs.override_router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(whitelist.router, prefix="/api/v1")
app.include_router(assessments.router, prefix="/api/v1")
app.include_router(student_assessments.router, prefix="/api/v1")


@app.get("/")
def read_root():
    """Root endpoint"""
    return {"message": "SQL Learning Platform API", "version": "1.0.0"}


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
