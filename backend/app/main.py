from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.config import settings
from app.database import engine, Base
from app.api.v1.endpoints import auth, questions, execute, attempts, chatbot, er_diagram, labs, problems, sql_lab_questions, graph_questions, users, whitelist
# Import models to register them with SQLAlchemy
from app.models.user import User
from app.models.whitelist import WhitelistEntry
from app.models.question import Question
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.attempt import Attempt
from app.models.progress import UserProgress
from app.models.lab import Lab
from app.models.lab_item import LabItem
from app.models.lab_submission import LabSubmission
from app.models.lab_session import LabSession
from app.models.lab_attempt import LabAttempt
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.sql_lab_question import SqlLabQuestion, SqlLabTask
from app.models.graph_question import GraphQuestion, GraphTask

# Drop the broken non-partial unique index if it exists so create_all recreates it
# correctly as a partial index (WHERE is_active = 1). This fixes SQLite ignoring
# postgresql_where, which caused IntegrityError when creating a second session.
with engine.connect() as _conn:
    _conn.execute(text("DROP INDEX IF EXISTS uq_active_session_per_user_lab"))
    _conn.commit()

# Auto-create tables on startup (safe for SQLite; for PostgreSQL use create_tables.py)
Base.metadata.create_all(bind=engine)

# Add lab_type column if it doesn't exist (handles existing local SQLite databases)
with engine.connect() as _conn:
    try:
        _conn.execute(text("ALTER TABLE labs ADD COLUMN lab_type VARCHAR(10) NOT NULL DEFAULT 'sql'"))
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
app.include_router(problems.router, prefix="/api/v1")
app.include_router(sql_lab_questions.router, prefix="/api/v1")
app.include_router(graph_questions.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(whitelist.router, prefix="/api/v1")


@app.get("/")
def read_root():
    """Root endpoint"""
    return {"message": "SQL Learning Platform API", "version": "1.0.0"}


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
