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


class GoogleAuthRequest(BaseModel):
    """Google SSO login request — contains the Google ID token"""
    token: str


class MicrosoftAuthRequest(BaseModel):
    """Microsoft SSO login request — contains the Microsoft (Entra ID) ID token"""
    token: str


class DevLoginRequest(BaseModel):
    """Local-development login request — the email of an existing user.

    No credential is supplied: the endpoint that consumes this is gated on
    DEV_LOGIN_ENABLED plus a loopback-only check. See auth.dev_login.
    """
    email: EmailStr