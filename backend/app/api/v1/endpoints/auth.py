from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole
from app.models.whitelist import WhitelistEntry
from app.schemas.auth import GoogleAuthRequest, MicrosoftAuthRequest, DevAuthRequest, Token
from app.schemas.user import UserResponse
from app.core.security import verify_google_token, verify_microsoft_token, create_access_token
from app.core.cache import cache_read, Ns
from app.dependencies import get_current_user
from app.services.login_activity import record_login_day
from app.services import platform_usage

router = APIRouter(prefix="/auth", tags=["authentication"])


def _upsert_user_and_issue_token(email: str, entry: dict, db: Session) -> dict:
    """Create/update the User for an authenticated email and mint its JWT.

    ``entry`` carries role/name/class_group — from the whitelist for SSO
    logins, synthesized for the dev login. Shared tail of every login path:
    profile sync, login-day recording, platform-usage session, token.

    Callers must pass ``email`` already lowercased.
    """
    user = db.query(User).filter(User.email == email).first()
    if user:
        if user.role != entry["role"]:
            user.role = entry["role"]
        # Sync profile info from the provider entry
        user.name = entry["name"]
        user.class_group = entry["class_group"]
        user.is_active = 1
    else:
        user = User(
            email=email,
            hashed_password="",
            role=entry["role"],
            name=entry["name"],
            class_group=entry["class_group"],
            is_active=1,
        )
        db.add(user)

    db.commit()
    db.refresh(user)

    # Record today's (SGT) login day for the streak/calendar feature. Students
    # only; at most one row per calendar day. Never blocks the login — the helper
    # swallows its own errors.
    record_login_day(db, user)

    # Open a platform-time session and embed its id as the ``sid`` claim so each
    # authenticated action can advance its own session's last_action_at. Covers
    # every role (the /admin "Active Now" split counts staff too). Returns None
    # only on failure — login proceeds either way.
    sid = platform_usage.start_session(db, user)

    token_data = {"sub": user.email, "role": user.role.value}
    if sid is not None:
        token_data["sid"] = sid
    access_token = create_access_token(data=token_data)
    return {"access_token": access_token, "token_type": "bearer"}


def _issue_token_for_whitelisted_email(email: str, db: Session) -> dict:
    """Shared SSO login logic used by every identity provider.

    Given an authenticated email address, validates it against the whitelist,
    creates or updates the corresponding User (syncing role/name/class_group from
    the whitelist entry), and returns a signed JWT access-token response.

    Only the email is used to decide whether the user may log in. Raises 403 if the
    email is not whitelisted.
    """
    email = email.lower()

    def _lookup_whitelist_entry() -> dict | None:
        # Fully serialize while the session is open -- a cached payload must never
        # be a session-bound ORM row (see app.core.cache module docstring).
        entry = db.query(WhitelistEntry).filter(WhitelistEntry.email == email).first()
        if not entry:
            return None
        return {"role": entry.role, "name": entry.name, "class_group": entry.class_group}

    entry = cache_read(db, Ns.WHITELIST, key=("email", email), producer=_lookup_whitelist_entry)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access not granted. Contact your administrator.",
        )

    return _upsert_user_and_issue_token(email, entry, db)


@router.post("/google", response_model=Token)
def google_login(
    request: GoogleAuthRequest,
    db: Session = Depends(get_db),
):
    payload = verify_google_token(request.token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token",
        )

    email: str = payload.get("email", "")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token missing email",
        )

    return _issue_token_for_whitelisted_email(email, db)


@router.post("/microsoft", response_model=Token)
def microsoft_login(
    request: MicrosoftAuthRequest,
    db: Session = Depends(get_db),
):
    payload = verify_microsoft_token(request.token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Microsoft token",
        )

    # The Azure App registration is configured to return the user's email. Fall back
    # to preferred_username (a UPN, which is email-shaped) only when it is a real email.
    email: str = payload.get("email") or payload.get("preferred_username") or ""
    if "@" not in email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Microsoft token missing email",
        )

    return _issue_token_for_whitelisted_email(email, db)


@router.post("/dev", response_model=Token, include_in_schema=settings.DEV_LOGIN_ENABLED)
def dev_login(
    request: DevAuthRequest,
    db: Session = Depends(get_db),
):
    """Development-only login: pick a role, get a real session.

    Bypasses SSO and the whitelist, so it must never be enabled in production —
    when DEV_LOGIN_ENABLED is off (the default) it answers 404 and is left out
    of the OpenAPI schema.
    """
    if not settings.DEV_LOGIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    role = request.role
    # A custom email deliberately lets a dev impersonate an existing local
    # account (and role-hop it). Fine against the local sqlite DB — never point
    # a dev box with this flag at a shared database.
    # example.com, not .test/.local: UserResponse.email is EmailStr, and
    # pydantic's validator rejects special-use TLDs — /auth/me would 500.
    email = (request.email or f"dev-{role.value}@example.com").lower()
    entry = {
        "role": role,
        "name": f"Dev {role.value.capitalize()}",
        "class_group": "TEST",   # excluded from assessment-registration ratios and the research export
    }
    return _upsert_user_and_issue_token(email, entry, db)


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user