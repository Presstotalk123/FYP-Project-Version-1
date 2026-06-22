from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class ErLab(Base):
    __tablename__ = "er_labs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)

    # bcrypt hash; plain stored so staff can re-display the join code from the settings page
    join_password_hash = Column(String(255), nullable=False)
    join_password_plain = Column(String(255), nullable=False)

    is_published = Column(Integer, default=0)
    is_running = Column(Integer, default=0)

    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    is_deleted = Column(Integer, default=0)
