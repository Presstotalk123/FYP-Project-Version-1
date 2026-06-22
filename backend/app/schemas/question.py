from pydantic import BaseModel, Field
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
    correct_answer_query: str = Field(..., description="SELECT query for correct answer")


class QuestionUpdate(BaseModel):
    """Schema for updating a question"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    difficulty: Optional[Difficulty] = None
    schema_sql: Optional[str] = None
    sample_data_sql: Optional[str] = None
    correct_answer_query: Optional[str] = None


class QuestionResponse(QuestionBase):
    """Schema for question response (without sensitive data)"""
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QuestionDetail(QuestionResponse):
    """Schema for detailed question view (includes SQL)"""
    schema_sql: str
    sample_data_sql: str
    db_file_path: str

    class Config:
        from_attributes = True


class QuestionListItem(BaseModel):
    """Schema for question list items"""
    id: int
    title: str
    difficulty: Difficulty
    created_at: datetime

    class Config:
        from_attributes = True
