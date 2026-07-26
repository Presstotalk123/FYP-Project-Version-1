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
    GOOGLE_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_TENANT_ID: str = "common"

    # Question databases path
    QUESTION_DB_PATH: str = "./question_databases/"

    # Lab databases path
    LAB_DB_PATH: str = "./lab_databases/"

    # AI Chatbot (existing Dify integration)
    DIFY_API_KEY: str

    # AI Query Review — configurable provider
    # Supported values: "azure_openai" | "openai" | "gemini"
    AI_PROVIDER: str = "azure_openai"
    AI_API_KEY: str = ""
    AI_MODEL: str = "gpt-4o-mini"           # Azure deployment name or model ID
    AI_TEMPERATURE: Optional[float] = None  # Optional temperature override
    AI_ENABLE_TEMPERATURE: bool = True      # Set to False to disable passing temperature (e.g., for o1/o3/gpt-5 models)
    AI_AZURE_ENDPOINT: str = ""             # https://<resource>.openai.azure.com/
    AI_AZURE_API_VERSION: str = "2024-02-01"

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "https://proud-stone-0ec93a000.2.azurestaticapps.net"
    ]

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

    # ERD tutor engine selector: "dify" (legacy) | "langgraph" (new)
    ERD_TUTOR_ENGINE: str = "dify"

    # ERD rubric-generation engine selector: "dify" (legacy) | "langgraph" (new)
    ERD_RUBRIC_ENGINE: str = "dify"

    # Azure OpenAI for the ERD LangGraph engines (tutor + rubric generator).
    # ERD_-prefixed so the scope is explicit; values are deployment NAMES from
    # the Azure OpenAI resource. (No api-version setting: the code talks to
    # Azure's unified v1 surface, which has none.)
    ERD_AZURE_OPENAI_ENDPOINT: Optional[str] = None
    ERD_AZURE_OPENAI_API_KEY: Optional[str] = None
    ERD_AZURE_OPENAI_VISION_DEPLOYMENT: str = "gpt-5.4"
    ERD_AZURE_OPENAI_GRADE_DEPLOYMENT: str = "gpt-5.4-mini"
    ERD_AZURE_OPENAI_TUTOR_DEPLOYMENT: str = "gpt-5.4-nano"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
