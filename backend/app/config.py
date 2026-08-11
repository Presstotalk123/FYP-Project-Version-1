from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    DATABASE_URL: str = "sqlite:///./sql_learning.db"

    # Connection-pool sizing (PostgreSQL only). Defaults are tuned for Azure
    # Database for PostgreSQL *Burstable/base* tier, which allows only ~50
    # max_connections (~35 after Azure's own reservations). With N gunicorn
    # workers the server sees up to N*(DB_POOL_SIZE + DB_MAX_OVERFLOW)
    # connections, so keep workers*(pool+overflow) under ~35 unless the
    # built-in PgBouncer (port 6432, transaction mode) is enabled.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 10       # seconds to wait for a free connection, then fail fast
    DB_POOL_RECYCLE: int = 1800     # recycle before Azure reaps idle connections

    # Upper bound on concurrent sync (`def`) endpoint handlers. FastAPI runs
    # them in a threadpool that defaults to 40; raised so a burst of student
    # "Run" clicks queues less. Each concurrent handler may run one SQLite
    # query, so size this to the App Service instance's CPU headroom.
    THREADPOOL_MAX_THREADS: int = 100

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    GOOGLE_CLIENT_ID: str = ""

    # Microsoft SSO (Azure Entra ID / Microsoft Identity Platform)
    # Use "common" for the tenant to allow any Microsoft account (work/school
    # or personal). MICROSOFT_CLIENT_ID is the Azure App registration's
    # Application (client) ID; ID tokens are validated against it as the audience.
    MICROSOFT_CLIENT_ID: str = ""
    MICROSOFT_TENANT_ID: str = "common"

    # Question databases path
    QUESTION_DB_PATH: str = "./question_databases/"

    # Lab databases path
    LAB_DB_PATH: str = "./lab_databases/"

    # AI Chatbot — legacy Dify key (no longer used by SQL-questions tutor;
    # kept optional so deployments without it still start)
    DIFY_API_KEY: str = ""

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
        "https://zealous-stone-03626e900.7.azurestaticapps.net",
        "https://ntuakela.net",
        "https://www.ntuakela.net"
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
    # Per-request timeout (seconds) for the LangGraph ERD tutor/rubric LLM calls,
    # mirroring DIFY_ER_*_TIMEOUT_SECONDS. Bounds a hung upstream call so it can't
    # tie up the request indefinitely (max_retries=3 is set separately on the client).
    ERD_AZURE_OPENAI_TIMEOUT_SECONDS: int = 60
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()