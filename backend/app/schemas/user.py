from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr


class UserCreate(UserBase):
    """Schema for creating a new user"""
    password: str
    role: UserRole = UserRole.STUDENT


class UserResponse(UserBase):
    """Schema for user response"""
    id: int
    role: UserRole
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class UserInDB(UserBase):
    """Schema for user in database"""
    id: int
    hashed_password: str
    role: UserRole
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True
