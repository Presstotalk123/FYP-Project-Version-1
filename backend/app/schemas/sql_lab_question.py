from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.question import Difficulty


class SqlLabTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    correct_query: str = Field(..., min_length=1)


class SqlLabQuestionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    difficulty: Difficulty
    schema_sql: str = Field(..., min_length=1)
    sample_data_sql: str = Field(..., min_length=1)
    tasks: List[SqlLabTaskCreate] = Field(..., min_length=1)


class SqlLabTaskView(BaseModel):
    id: int
    title: str
    description: str
    order_index: int
    has_answer: bool

    class Config:
        from_attributes = True


class SqlLabQuestionResponse(BaseModel):
    id: int
    title: str
    description: str
    difficulty: str
    schema_sql: str
    sample_data_sql: str
    created_by: int
    created_at: datetime
    tasks: List[SqlLabTaskView]


class SqlLabQuestionListItem(BaseModel):
    id: int
    title: str
    difficulty: str
    task_count: int
    created_by: int
    created_at: datetime


class SqlLabPracticeSubmit(BaseModel):
    """Submit a task answer while solving a SQL-lab question standalone (outside a lab)."""
    query: str = Field(..., min_length=1)
    task_id: int
