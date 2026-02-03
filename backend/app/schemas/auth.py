from pydantic import BaseModel, EmailStr
from typing import Optional
from app.models.user import UserRole


class Token(BaseModel):
    """JWT token response schema"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Data stored in JWT token"""
    email: Optional[str] = None
    role: Optional[UserRole] = None


class LoginRequest(BaseModel):
    """Login request schema"""
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """Registration request schema"""
    email: EmailStr
    password: str
    role: UserRole = UserRole.STUDENT
