"""Schemas for the course-info endpoints (student read + staff edit)."""

from pydantic import BaseModel, Field

# Generous ceiling on the Markdown document; mirrors MAX_PROMPT_CHARS in erd_prompts.
MAX_COURSE_INFO_CHARS = 50_000


class CourseInfoResponse(BaseModel):
    content: str


class CourseInfoUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_COURSE_INFO_CHARS)
