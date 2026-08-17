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

    # Active-user count on /admin (see docs/superpowers/specs/2026-08-14-active-user-count-design.md).
    # BEAT is how often an idle-but-visible tab checks in; WINDOW is how long a
    # stale last_action_at still counts as online. WINDOW must stay >=
    # 2 * BEAT + 60 (the touch_session write throttle), or one delayed beat
    # makes a user flicker offline.
    PRESENCE_BEAT_SECONDS: int = 600
    PRESENCE_WINDOW_SECONDS: int = 1500

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    GOOGLE_CLIENT_ID: str = ""

    # HMAC-SHA256 salt for anonymizing student ids in the research CSV export
    # (app/api/v1/endpoints/research_export.py). Required — the raw-csv endpoint
    # refuses to run (503) without it, so a forgotten env var can't ship a weakly
    # anonymized export. No reversible mapping is stored anywhere; rotating this salt
    # permanently changes every anon_id.
    RESEARCH_EXPORT_SALT: str = ""

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

    # Class groups that are staff/test accounts rather than real participants. Excluded from
    # BOTH sides of every analytics ratio — the registered denominator and the roster
    # numerator — so a tutor sitting an assessment to check it does not skew the cohort
    # average or produce "13/12 attempted".
    ANALYTICS_EXCLUDED_CLASS_GROUPS: list[str] = ["TEST", "TA", "PROF"]

    # Accounts confined to a fixed subset of backend endpoints regardless of
    # their DB role, and the path prefixes they're allowed to hit. Enforced
    # by the restrict_limited_users middleware in main.py. Emails compared
    # case-insensitively.
    RESTRICTED_USER_EMAILS: set[str] = {"qichen.wang@ntu.edu.sg", "mysterystudent007@gmail.com"}
    RESTRICTED_USER_ALLOWED_PATH_PREFIXES: tuple[str, ...] = (
        "/api/v1/auth",       # must stay open, otherwise the user can't log in
        "/api/v1/questions",  # SQL Questions authoring
        "/api/v1/labs",       # SQL Lab authoring
    )

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

    # --- Akela multi-agent / learning-analytics platform ---------------------
    # Two independent flags so telemetry + mastery can be built and validated
    # dark (writing learning_events silently) before any student-facing chat
    # behavior changes. Instant rollback via env var, mirroring ERD_TUTOR_ENGINE.
    #
    # AKELA_AGENTS_ENABLED: master switch for learning-event logging and the
    #   background Learner Profiling / SOLO Classifier agents. When False, none
    #   of that machinery runs and the platform behaves exactly as before.
    # SQL_TUTOR_ADAPTIVE: when True, the SQL chatbot's /send + /lab-chat use
    #   adaptive prompt construction (mastery/scaffolding lookup); when False the
    #   existing stateless single-shot prompts are used.
    AKELA_AGENTS_ENABLED: bool = False
    SQL_TUTOR_ADAPTIVE: bool = False

    # Azure OpenAI for the SOLO classifier (reuses the ERD v1-surface approach;
    # SQL_-prefixed so the scope is explicit). Falls back to the generic AI_*
    # settings when unset — see app.services.solo_classifier.
    SQL_AZURE_OPENAI_ENDPOINT: Optional[str] = None
    SQL_AZURE_OPENAI_API_KEY: Optional[str] = None
    SQL_AZURE_OPENAI_TUTOR_DEPLOYMENT: str = "gpt-5.4-nano"
    SQL_AZURE_OPENAI_SOLO_DEPLOYMENT: str = "gpt-5.4-mini"

    # Mastery model tuning (deterministic Learner Profiling Agent). Per-attempt
    # additive deltas on mastery_level (0..1), scaled by the question_concepts weight.
    CONCEPT_MASTERY_SUCCESS_DELTA: float = 0.15
    CONCEPT_MASTERY_FAILURE_DELTA: float = 0.10

    # Adaptive scaffolding transitions (per active concept).
    SCAFFOLDING_UPGRADE_STREAK: int = 3    # consecutive successes to fade support one level
    SCAFFOLDING_DOWNGRADE_STREAK: int = 2  # consecutive failures to restore support one level

    # SOLO classifier confidence gate: below this, fall back to a generic prompt.
    SOLO_CONFIDENCE_THRESHOLD: float = 0.6

    # Peer-benchmarking anonymization floor: suppress class averages for cohorts
    # smaller than this to prevent de-anonymization.
    PEER_BENCHMARK_MIN_COHORT: int = 5

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()