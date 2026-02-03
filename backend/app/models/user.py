from sqlalchemy import Column, Integer, String, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from app.database import Base
import enum


class UserRole(str, enum.Enum):
    """User role enumeration"""
    STUDENT = "student"
    STAFF = "staff"


class User(Base):
    """User model for authentication and authorization"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.STUDENT)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Integer, default=1)  # Using Integer for SQLite compatibility (0/1 for False/True)
