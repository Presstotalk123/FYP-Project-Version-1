from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserResponse, UserRoleUpdate, UserAddRequest, UserAddResponse, UserProfileUpdate
from app.core.security import hash_password
from app.dependencies import require_staff_role, require_admin_role

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
