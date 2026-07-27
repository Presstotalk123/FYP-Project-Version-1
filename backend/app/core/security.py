from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import JWTError, jwt
import jwt as pyjwt  # PyJWT — used for Microsoft ID-token verification (JWKS)
from jwt import PyJWKClient
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from app.config import settings
from app.models.user import UserRole


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Data to encode in the token (typically email and role)
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    return encoded_jwt


def verify_google_token(token: str) -> Optional[dict]:
    """Verify a Google ID token and return the payload (contains 'email', 'name', etc.)."""
    try:
        return google_id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
        )
    except Exception:
        return None


# Lazily-created JWKS client for the Microsoft identity platform. The constructor
# performs no network I/O (keys are fetched and cached on first use), so it is safe
# to build once at module scope.
_microsoft_jwks_client: Optional[PyJWKClient] = None


def _get_microsoft_jwks_client() -> PyJWKClient:
    global _microsoft_jwks_client
    if _microsoft_jwks_client is None:
        jwks_url = (
            f"https://login.microsoftonline.com/"
            f"{settings.MICROSOFT_TENANT_ID}/discovery/v2.0/keys"
        )
        _microsoft_jwks_client = PyJWKClient(jwks_url)
    return _microsoft_jwks_client


def verify_microsoft_token(token: str) -> Optional[dict]:
    """Verify a Microsoft (Entra ID) ID token and return its claims.

    Security checks performed:
      * RS256 signature validated against the Microsoft identity platform JWKS.
      * Audience must equal our app's MICROSOFT_CLIENT_ID.
      * Expiry ('exp') is validated by PyJWT.
      * Issuer is validated against the Microsoft issuer for the token's own tenant.
        (With the "common" endpoint the tenant varies per user, so the issuer cannot
        be a single fixed value — we bind it to the token's `tid` claim instead.)

    Returns the decoded claims (contains 'email'/'preferred_username', etc.) or None
    if the token is missing/invalid.
    """
    if not settings.MICROSOFT_CLIENT_ID:
        return None

    try:
        signing_key = _get_microsoft_jwks_client().get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.MICROSOFT_CLIENT_ID,
            # Issuer is tenant-specific under "common"; validated manually below.
            options={"verify_iss": False},
        )
    except Exception:
        return None

    tenant_id = payload.get("tid")
    issuer = payload.get("iss", "")
    if not tenant_id or issuer != f"https://login.microsoftonline.com/{tenant_id}/v2.0":
        return None

    return payload


def decode_token(token: str) -> Optional[dict]:
    """
    Decode and verify a JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded token data or None if invalid
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None