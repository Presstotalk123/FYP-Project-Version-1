from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import Optional
from app.models.question import Difficulty


class QuestionBase(BaseModel):
    """Base question schema"""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    difficulty: Difficulty


class QuestionCreate(QuestionBase):
    """Schema for creating a new question"""
    schema_sql: str = Field(..., description="CREATE TABLE statements")
    sample_data_sql: str = Field(..., description="INSERT statements")
    # A SELECT query in standard mode; an arbitrary reference implementation
    # (e.g. CREATE TRIGGER ...) when advanced_sql_testing is enabled.
    correct_answer_query: str = Field(..., description="Correct answer query / reference implementation")
    advanced_sql_testing: bool = Field(False, description="Staff-only: grade via hidden Test Script + Check Query instead of direct output comparison")
    test_script: Optional[str] = Field(None, description="Staff-only hidden script that exercises the submission (e.g. an INSERT that fires a trigger)")
    check_query: Optional[str] = Field(None, description="Staff-only hidden SELECT that captures the resulting state to hash")
    hide_correctness: bool = Field(False, description="When on, students see a neutral 'Submitted' result instead of Correct/Incorrect")

    @model_validator(mode="after")
    def _validate_advanced_fields(self):
        if self.advanced_sql_testing:
            if not self.test_script or not self.test_script.strip():
                raise ValueError("Test Script is required when Advanced SQL Testing is enabled")
            if not self.check_query or not self.check_query.strip():
                raise ValueError("Check Query is required when Advanced SQL Testing is enabled")
        return self


class QuestionUpdate(BaseModel):
    """Schema for updating a question"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    difficulty: Optional[Difficulty] = None
    schema_sql: Optional[str] = None
    sample_data_sql: Optional[str] = None
    correct_answer_query: Optional[str] = Field(None, min_length=1)
    advanced_sql_testing: Optional[bool] = None
    test_script: Optional[str] = None
    check_query: Optional[str] = None
    hide_correctness: Optional[bool] = None


class QuestionResponse(QuestionBase):
    """Schema for question response (without sensitive data)"""
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    advanced_sql_testing: bool = False
    test_script: Optional[str] = None
    check_query: Optional[str] = None
    hide_correctness: bool = False
    is_published: bool = False

    class Config:
        from_attributes = True


class QuestionDetail(QuestionResponse):
    """Schema for detailed question view (includes SQL)"""
    schema_sql: str
    sample_data_sql: str
    db_file_path: str
    # Only supplied to staff/admin users by the detail endpoint.
    correct_answer_query: Optional[str] = None

    class Config:
        from_attributes = True


class QuestionListItem(BaseModel):
    """Schema for question list items"""
    id: int
    title: str
    difficulty: Difficulty
    created_at: datetime
    is_published: bool = False

    class Config:
        from_attributes = True


class QuestionCountResponse(BaseModel):
    """Counts for the student dashboard SQL tile.

    `total` is the size of the student-visible question bank (cached in-process,
    identical across students); `attempted` is how many of those the current user
    has an attempt on (per-user, computed live)."""
    total: int
    attempted: int
