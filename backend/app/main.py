from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import engine, Base
from app.api.v1.endpoints import auth, questions, execute, attempts
# Import models to register them with SQLAlchemy
from app.models.user import User
from app.models.question import Question
from app.models.attempt import Attempt
from app.models.progress import UserProgress

# Create database tables
Base.metadata.create_all(bind=engine)

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


@app.get("/")
def read_root():
    """Root endpoint"""
    return {"message": "SQL Learning Platform API", "version": "1.0.0"}


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
