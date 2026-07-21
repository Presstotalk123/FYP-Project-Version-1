from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly).
from app.models import user as _user  # noqa: F401


class ErdPromptVersion(Base):
    __tablename__ = "erd_prompt_versions"
    __table_args__ = (
        Index("ix_erd_prompt_key_active", "prompt_key", "is_active"),
        UniqueConstraint("prompt_key", "version_no", name="uq_erd_prompt_key_version"),
    )
    id = Column(Integer, primary_key=True, index=True)
    prompt_key = Column(String(40), nullable=False, index=True)  # key in PROMPT_REGISTRY
    version_no = Column(Integer, nullable=False)                 # per-key, from 1
    content = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # invariant: at most one active row per prompt_key; zero active = code default
    is_active = Column(Integer, nullable=False, default=0)
