"""Schemas for the course-info endpoints (student read + staff edit)."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

# Generous ceiling on the Markdown document; mirrors MAX_PROMPT_CHARS in erd_prompts.
MAX_COURSE_INFO_CHARS = 50_000


class CourseInfoResponse(BaseModel):
    content: str
    updated_at: Optional[datetime] = None
    updated_by_email: Optional[str] = None


class CourseInfoUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_COURSE_INFO_CHARS)
