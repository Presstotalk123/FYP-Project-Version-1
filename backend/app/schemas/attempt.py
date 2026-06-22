from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class ExecuteRequest(BaseModel):
    """Schema for query execution request"""
    question_id: int = Field(..., description="Question ID to execute query against")
    query: str = Field(..., min_length=1, description="SQL query to execute")


class ExecuteResponse(BaseModel):
    """Schema for query execution response"""
    is_correct: bool
    execution_time_ms: float
    results: List[Dict[str, Any]]
    columns: List[str]
    error_message: Optional[str] = None
    row_count: int


class AttemptCreate(BaseModel):
    """Schema for creating an attempt record"""
    user_id: int
    question_id: int
    query: str
    is_correct: bool
    execution_time_ms: Optional[float] = None
    error_message: Optional[str] = None


class AttemptResponse(BaseModel):
    """Schema for attempt response"""
    id: int
    user_id: int
    question_id: int
    query: str
    is_correct: bool
    execution_time_ms: Optional[float]
    error_message: Optional[str]
    submitted_at: datetime

    class Config:
        from_attributes = True


class AttemptHistory(BaseModel):
    """Schema for attempt history with question info"""
    id: int
    question_id: int
    question_title: str
    query: str
    is_correct: bool
    execution_time_ms: Optional[float]
    submitted_at: datetime

    class Config:
        from_attributes = True


class ProgressResponse(BaseModel):
    """Schema for user progress response"""
    question_id: int
    question_title: str
    completed: bool
    attempts_count: int
    last_attempted_at: Optional[datetime]
    first_completed_at: Optional[datetime]
