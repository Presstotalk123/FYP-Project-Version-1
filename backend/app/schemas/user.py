from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from app.models.user import UserRole


class UserBase(BaseModel):
    """Base user schema"""
    email: EmailStr
    name: Optional[str] = None
    class_group: Optional[str] = None


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


class UserProfileUpdate(BaseModel):
    """Schema for updating a user's optional profile fields"""
    name: Optional[str] = None
    class_group: Optional[str] = None


class UserInDB(UserBase):
    """Schema for user in database"""
    id: int
    hashed_password: str
    role: UserRole
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserAddRequest(BaseModel):
    email: EmailStr
    role: UserRole


class UserAddResponse(BaseModel):
    user: UserResponse
    temp_password: str | None = None
