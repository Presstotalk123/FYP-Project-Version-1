from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Dict, List
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserResponse, UserRoleUpdate, UserAddRequest, UserAddResponse, UserProfileUpdate
from app.core.security import hash_password
from app.dependencies import get_current_user, require_staff_role, require_admin_role
from app.services import user_preferences

router = APIRouter(prefix="/users", tags=["users"])

TEMP_PASSWORD = "TempPass@123"


@router.get("", response_model=List[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_staff_role),
):
    return db.query(User).all()


@router.post("/add", response_model=UserAddResponse)
def add_user_to_role(
    request: UserAddRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_role),
):
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        existing.role = request.role
        db.commit()
        db.refresh(existing)
        return UserAddResponse(user=existing, temp_password=None)

    new_user = User(
        email=request.email,
        hashed_password=hash_password(TEMP_PASSWORD),
        role=request.role,
        is_active=1,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserAddResponse(user=new_user, temp_password=TEMP_PASSWORD)


@router.patch("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int,
    request: UserRoleUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_role),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.role = request.role
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_role),
):
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(user)
    db.commit()


@router.patch("/{user_id}/profile", response_model=UserResponse)
def update_user_profile(
    user_id: int,
    request: UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Update a user's name and/or class group. Pass null to clear a field."""
    # Allow staff/admin to update any user, or a user to update themselves
    if current_user.role == "student" and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own profile"
        )
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.name = request.name
    user.class_group = request.class_group
    db.commit()
    db.refresh(user)
    return user


# ---- the current user's own UI preferences ----------------------------------
# Declared before the /{user_id}/... routes only for readability; the paths do
# not overlap ("me/preferences" is two segments, those are "{user_id}/role" and
# "{user_id}/profile"). Any logged-in user, own row only — nothing here can
# read or write another user's preferences.


class PreferenceValue(BaseModel):
    value: str = Field(max_length=user_preferences.MAX_VALUE_LENGTH)


@router.get("/me/preferences", response_model=Dict[str, str])
def get_my_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every preference the current user has set, keyed by name. Missing keys
    mean "unset" — the frontend applies its own default."""
    return user_preferences.get_all(db, user_id=current_user.id)


@router.put("/me/preferences/{key}", status_code=status.HTTP_204_NO_CONTENT)
def set_my_preference(
    key: str,
    body: PreferenceValue,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        user_preferences.set_value(db, user_id=current_user.id, key=key, value=body.value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

