from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

# Create SQLAlchemy engine with conditional configuration
if "postgresql" in settings.DATABASE_URL:
    # PostgreSQL configuration with connection pooling.
    #
    # Pool sizes come from settings so they can be tuned per deployment without
    # a code change. Defaults are sized for Azure Postgres Burstable/base tier
    # (~35 usable connections total): with 2 workers that's 2*(5+5)=20 < 35.
    # pool_timeout is short so an exhausted pool fails fast with a clear error
    # instead of hanging the request for 30s.
    #
    # keepalives keep otherwise-idle pooled connections from being silently
    # dropped by Azure's network idle timeout (which later surfaces as a stall
    # on the next checkout); pool_pre_ping is the second line of defense.
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,                      # verify a connection before handing it out
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        connect_args={
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    )
else:
    # SQLite configuration
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False, "timeout": 15}
    )

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency function to get database session.
    Yields a database session and closes it after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
