from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = "sqlite:///./sql_learning.db"

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # Question databases path
    QUESTION_DB_PATH: str = "./question_databases/"

    # AI Chatbot
    DIFY_API_KEY: str

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Dify ER rubric endpoint
    DIFY_ER_RUBRIC_URL: Optional[str] = None
    DIFY_ER_RUBRIC_API_KEY: Optional[str] = None
    DIFY_ER_RUBRIC_TIMEOUT_SECONDS: int = 60
    DIFY_ER_SUBMISSION_URL: Optional[str] = None
    DIFY_ER_SUBMISSION_API_KEY: Optional[str] = None
    DIFY_ER_SUBMISSION_TIMEOUT_SECONDS: int = 60

    # ER model answer storage
    ER_STORAGE_PROVIDER: str = "local"
    ER_DIAGRAM_UPLOAD_PATH: str = "./er_diagram_uploads/"
    ER_AZURE_CONTAINER: Optional[str] = None
    ER_AZURE_CONNECTION_STRING: Optional[str] = None
    ER_AZURE_ACCOUNT_URL: Optional[str] = None
    ER_AZURE_ACCOUNT_KEY: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
