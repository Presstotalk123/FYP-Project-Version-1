from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401


class AppSetting(Base):
    """A single admin-tunable application setting.

    Deliberately a key/value row rather than a column per toggle: settings are
    read rarely, written rarely, and adding one should not require a migration.
    A missing row means "use the code default", which keeps defaults in Python
    where they can be reviewed.
    """

    __tablename__ = "app_settings"

    key = Column(String(80), primary_key=True)
    value = Column(Text, nullable=False)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
