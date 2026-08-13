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


class ParsedStudent(BaseModel):
    """A single row parsed from an uploaded roster sheet, echoed back by the
    frontend on /whitelist/upload/confirm so the server can re-derive the
    diff itself rather than trusting client-side classification."""
    name: str
    email: EmailStr
    class_group: Optional[str] = None


class UploadAddition(BaseModel):
    email: str
    name: Optional[str] = None
    class_group: Optional[str] = None


class UploadUpdate(BaseModel):
    id: int
    email: str
    old_name: Optional[str] = None
    new_name: Optional[str] = None
    old_class_group: Optional[str] = None
    new_class_group: Optional[str] = None


class UploadRemoval(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    class_group: Optional[str] = None


class UploadPreviewResponse(BaseModel):
    to_add: list[UploadAddition]
    to_update: list[UploadUpdate]
    to_remove: list[UploadRemoval]
    failed: list[dict]
    students: list[ParsedStudent]


class UploadConfirmRequest(BaseModel):
    students: list[ParsedStudent]
    confirm_removals: bool = False


class UploadConfirmResponse(BaseModel):
    imported: int
    updated: int
    removed: int
    failed: list[dict]
