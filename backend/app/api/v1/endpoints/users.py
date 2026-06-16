from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse
from app.dependencies import require_staff_role

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=List[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_staff_role),
):
    return db.query(User).all()
