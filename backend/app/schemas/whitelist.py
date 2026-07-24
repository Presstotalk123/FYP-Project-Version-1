from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional
from app.models.user import UserRole


class WhitelistEntryCreate(BaseModel):
    email: EmailStr
    role: UserRole
    name: Optional[str] = None
    class_group: Optional[str] = None


class WhitelistEntryUpdate(BaseModel):
    name: Optional[str] = None
    class_group: Optional[str] = None


class WhitelistEntryResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    name: Optional[str] = None
    class_group: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
