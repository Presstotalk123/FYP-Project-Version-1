from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.models.whitelist import WhitelistEntry
from app.schemas.auth import GoogleAuthRequest, Token
from app.schemas.user import UserResponse
from app.core.security import verify_google_token, create_access_token
from app.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["authentication"])


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

    email: str = payload.get("email", "").lower()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google token missing email",
        )

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


@router.get("/me", response_model=UserResponse)
def get_current_user_info(current_user: User = Depends(get_current_user)):
    return current_user
