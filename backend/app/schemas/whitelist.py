from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional
from app.models.user import UserRole

# Length caps mirror the DB columns (see app/models/whitelist.py and app/models/user.py):
# email VARCHAR(255), name VARCHAR(255), class_group VARCHAR(100).
EMAIL_MAX = 255
NAME_MAX = 255
CLASS_GROUP_MAX = 100


class WhitelistEntryCreate(BaseModel):
    email: EmailStr = Field(..., max_length=EMAIL_MAX)
    role: UserRole
    name: Optional[str] = Field(None, max_length=NAME_MAX)
    class_group: Optional[str] = Field(None, max_length=CLASS_GROUP_MAX)


class WhitelistEntryUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=NAME_MAX)
    class_group: Optional[str] = Field(None, max_length=CLASS_GROUP_MAX)


class WhitelistEntryResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    name: Optional[str] = None
    class_group: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
