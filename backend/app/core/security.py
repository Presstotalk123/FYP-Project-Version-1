from datetime import datetime, timedelta
from typing import Optional
import time
import bcrypt
from jose import JWTError, jwt
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
from cryptography.hazmat.backends import default_backend
import base64
import requests
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


# ---------- Microsoft token verification ----------

# Cache for Microsoft JWKS keys (keys, fetched_at)
_ms_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}
_MS_JWKS_CACHE_TTL = 3600  # 1 hour


def _ensure_bytes(value: str) -> bytes:
    """Base64url-decode a string, adding padding as needed."""
    value = value.replace("-", "+").replace("_", "/")
    padding = 4 - len(value) % 4
    if padding != 4:
        value += "=" * padding
    return base64.b64decode(value)


def _get_microsoft_jwks() -> list[dict]:
    """Fetch and cache Microsoft's JWKS public keys for the configured tenant."""
    now = time.time()
    if _ms_jwks_cache["keys"] and (now - _ms_jwks_cache["fetched_at"]) < _MS_JWKS_CACHE_TTL:
        return _ms_jwks_cache["keys"]

    tenant = settings.MICROSOFT_TENANT_ID or "common"
    discovery_url = f"https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
    discovery = requests.get(discovery_url, timeout=10).json()
    jwks_uri = discovery["jwks_uri"]
    jwks = requests.get(jwks_uri, timeout=10).json()

    _ms_jwks_cache["keys"] = jwks.get("keys", [])
    _ms_jwks_cache["fetched_at"] = now
    return _ms_jwks_cache["keys"]


def _get_rsa_public_key(kid: str):
    """Find the RSA public key matching the given key ID from Microsoft's JWKS."""
    keys = _get_microsoft_jwks()
    for key in keys:
        if key["kid"] == kid:
            n = int.from_bytes(_ensure_bytes(key["n"]), byteorder="big")
            e = int.from_bytes(_ensure_bytes(key["e"]), byteorder="big")
            return RSAPublicNumbers(e, n).public_key(default_backend())
    return None


def verify_microsoft_token(token: str) -> Optional[dict]:
    """Verify a Microsoft ID token and return the payload (contains 'email' / 'preferred_username', etc.)."""
    try:
        # Decode header to get key ID without verification first
        unverified_header = pyjwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        if not kid:
            return None

        public_key = _get_rsa_public_key(kid)
        if not public_key:
            return None

        tenant = settings.MICROSOFT_TENANT_ID or "common"
        # For multi-tenant ("common"), we must accept any issuer
        issuer = None if tenant == "common" else f"https://login.microsoftonline.com/{tenant}/v2.0"

        decode_options = {}
        if issuer is None:
            decode_options["verify_iss"] = False

        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.MICROSOFT_CLIENT_ID,
            issuer=issuer,
            options=decode_options,
        )
        return payload
    except Exception:
        return None


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

