from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.models.question import Difficulty


class GraphTaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    correct_query: str = Field(..., min_length=1)


class GraphQuestionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    difficulty: Difficulty
    seed_cypher: str = Field(..., min_length=1)
    tasks: List[GraphTaskCreate] = Field(..., min_length=1)


class GraphTaskView(BaseModel):
    id: int
    title: str
    description: str
    order_index: int
    has_answer: bool

    class Config:
        from_attributes = True


class GraphQuestionResponse(BaseModel):
    id: int
    title: str
    description: str
    difficulty: str
    seed_cypher: str
    created_by: int
    created_at: datetime
    tasks: List[GraphTaskView]


class GraphQuestionListItem(BaseModel):
    id: int
    title: str
    difficulty: str
    task_count: int
    created_by: int
    created_at: datetime


class GraphPracticeSubmit(BaseModel):
    """Submit a task answer while solving a graph question standalone (outside a lab)."""
    query: str = Field(..., min_length=1)
    task_id: int
