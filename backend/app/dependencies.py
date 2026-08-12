from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.security import decode_token
from app.models.user import User, UserRole
from app.schemas.auth import TokenData

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    """
    Get the current authenticated user from JWT token.

    Args:
        token: JWT access token from Authorization header
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode token
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception

    email: str = payload.get("sub")
    if email is None:
        raise credentials_exception

    token_data = TokenData(email=email, role=payload.get("role"))

    # Get user from database
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    return user


def get_current_sid(token: str = Depends(oauth2_scheme)) -> int | None:
    """The platform-session id (``sid``) embedded in the JWT at login, or ``None``.

    Used by the activity heartbeat to know which ``platform_sessions`` row to
    advance. Legacy tokens issued before this feature have no ``sid`` (the service
    falls back to the student's latest session); staff/admin tokens never carry one.
    Kept separate from ``get_current_user`` so that dependency stays read-only.
    """
    payload = decode_token(token)
    if payload is None:
        return None
    sid = payload.get("sid")
    return sid if isinstance(sid, int) else None


def require_staff_role(current_user: User = Depends(get_current_user)) -> User:
    """
    Require that the current user has staff or admin role.
    Admin inherits all staff privileges.
    """
    if current_user.role not in {UserRole.STAFF, UserRole.ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff role required"
        )

    return current_user


def require_admin_role(current_user: User = Depends(get_current_user)) -> User:
    """
    Require that the current user has admin role.
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required"
        )

    return current_user
