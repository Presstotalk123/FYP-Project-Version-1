from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class LabTaskCreate(BaseModel):
    """Schema for creating a new lab task (without answer)"""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    order_index: Optional[int] = Field(0, description="Display order")


class LabTaskAssignAnswer(BaseModel):
    """Schema for assigning an answer to a task"""
    query: str = Field(..., min_length=1, description="SQL query that produces correct answer")


class LabTaskUpdate(BaseModel):
    """Schema for updating a lab task"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    order_index: Optional[int] = None


class LabTaskResponse(BaseModel):
    """Schema for lab task response"""
    id: int
    lab_id: int
    title: str
    description: str
    order_index: int
    has_answer: bool  # Computed: whether correct_answer_hash is not null
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LabTaskDetail(LabTaskResponse):
    """Schema for detailed task view (staff only - includes correct query)"""
    correct_query: Optional[str] = None

    class Config:
        from_attributes = True


class LabTaskValidateRequest(BaseModel):
    """Schema for validating student answer"""
    task_id: int
    session_id: int
    user_query: str = Field(..., min_length=1)


class LabTaskValidateResponse(BaseModel):
    """Schema for validation response"""
    is_correct: bool
    message: str


class LabTaskSubmitRequest(BaseModel):
    """Schema for submitting student answer to a task"""
    task_id: int
    session_id: int
    columns: List[str] = Field(..., description="Column names from query result")
    results: List[dict] = Field(..., description="Query result rows")
    query: str = Field(..., min_length=1, description="The SQL query that produced these results")
    execution_time_ms: float
    row_count: int


class LabTaskSubmitResponse(BaseModel):
    """Schema for task submission response"""
    submission_id: int
    is_correct: bool
    message: str
    submitted_at: datetime


class LabTaskProgress(BaseModel):
    """Schema for individual task progress"""
    task_id: int
    is_completed: bool  # Has at least one correct submission
    attempt_count: int  # Total number of submissions
    last_submitted_at: Optional[datetime] = None


class LabTaskProgressResponse(BaseModel):
    """Schema for lab task progress response"""
    tasks: List[LabTaskProgress]
