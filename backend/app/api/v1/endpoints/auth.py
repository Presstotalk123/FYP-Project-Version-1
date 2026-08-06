from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.whitelist import WhitelistEntry
from app.schemas.auth import DevLoginRequest, GoogleAuthRequest, MicrosoftAuthRequest, Token
from app.schemas.user import UserResponse
from app.core.security import verify_google_token, verify_microsoft_token, create_access_token
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])

# Addresses that count as "the developer's own machine" for dev-login. A request
# arriving through any proxy or load balancer will not have one of these as its
# immediate peer, which is what makes the deployed app safe by construction.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def _issue_token_for_whitelisted_email(email: str, db: Session) -> dict:
    """Shared SSO login logic used by every identity provider.

    Given an authenticated email address, validates it against the whitelist,
    creates or updates the corresponding User (syncing role/name/class_group from
    the whitelist entry), and returns a signed JWT access-token response.

    Only the email is used to decide whether the user may log in. Raises 403 if the
    email is not whitelisted.
    """
    email = email.lower()

    entry = db.query(WhitelistEntry).filter(WhitelistEntry.email == email).first()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access not granted. Contact your administrator.",
        )

    user = db.query(User).filter(User.email == email).first()
    if user:
        if user.role != entry.role:
            user.role = entry.role
        # Sync profile info from whitelist
        user.name = entry.name
        user.class_group = entry.class_group
        user.is_active = 1
    else:
        user = User(
            email=email,
            hashed_password="",
            role=entry.role,
            name=entry.name,
            class_group=entry.class_group,
            is_active=1,
        )
        db.add(user)

    db.commit()
    db.refresh(user)

    access_token = create_access_token(data={"sub": user.email, "role": user.role.value})
    return {"access_token": access_token, "token_type": "bearer"}


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


@router.post("/dev-login", response_model=Token)
def dev_login(
    payload: DevLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """LOCAL DEVELOPMENT ONLY — issue a token for an existing user, no SSO.

    Exists so the app can be worked on offline, or when `localhost` is not a
    registered JavaScript origin on the Google OAuth client (which otherwise
    fails with `origin_mismatch`). It verifies no credential, so it is guarded
    three ways and every guard must pass:

      1. `DEV_LOGIN_ENABLED` must be true. It defaults to false, so an
         environment that never sets it cannot reach this code.
      2. The request's immediate peer must be loopback. Deployments sit behind a
         proxy, so their requests fail this even if (1) were set by mistake.
      3. The email must already exist in `users`. No account is created and no
         role is assigned here, so this cannot grant access that a person does
         not already have — it only skips the identity provider.

    Both guard failures return 404 rather than 403 so that a deployed instance
    is indistinguishable from one where the route does not exist.
    """
    if not settings.DEV_LOGIN_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    client_host = request.client.host if request.client else None
    if client_host not in _LOOPBACK_HOSTS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    email = payload.email.lower()
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active local user with that email. Sign in via SSO once, or seed the user first.",
        )

    access_token = create_access_token(data={"sub": user.email, "role": user.role.value})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user