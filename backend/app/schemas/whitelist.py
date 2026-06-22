from pydantic import BaseModel, EmailStr
from datetime import datetime
from app.models.user import UserRole


class WhitelistEntryCreate(BaseModel):
    email: EmailStr
    role: UserRole


class WhitelistEntryResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    created_at: datetime

    class Config:
        from_attributes = True
