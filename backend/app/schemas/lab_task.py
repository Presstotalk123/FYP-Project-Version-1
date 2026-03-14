from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


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
