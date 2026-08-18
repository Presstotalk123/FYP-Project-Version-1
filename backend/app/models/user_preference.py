from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base

# Import the FK target so its table is registered on Base.metadata when this
# model is imported on its own (as the migration script does).
from app.models import user as _user  # noqa: F401


class UserPreference(Base):
    """One per-user, per-key setting the UI remembers across devices.

    Key/value on purpose, like app_settings: the first tenant is the ER-diagram
    guide's "don't remind me again", and the next one (a SQL-workspace guide,
    say) should cost a new key, not a new column, migration and /auth/me field.
    Which keys are allowed is decided in services/user_preferences.py — the
    table is generic, the vocabulary is not.

    A missing row means "unset"; the code default lives in the frontend.
    """

    __tablename__ = "user_preferences"

    user_id = Column(Integer, ForeignKey("users.id"), primary_key=True)
    key = Column(String(80), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
