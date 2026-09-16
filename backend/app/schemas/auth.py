from pydantic import BaseModel
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


class GoogleAuthRequest(BaseModel):
    """Google SSO login request — contains the Google ID token"""
    token: str


class MicrosoftAuthRequest(BaseModel):
    """Microsoft SSO login request — contains the Microsoft (Entra ID) ID token"""
    token: str


class DevAuthRequest(BaseModel):
    """Development-only login request (POST /auth/dev; see DEV_LOGIN_ENABLED).

    No credential: the caller picks a role and optionally an email. Only ever
    served when DEV_LOGIN_ENABLED is on."""
    role: UserRole
    email: Optional[str] = None
