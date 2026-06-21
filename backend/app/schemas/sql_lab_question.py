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
    description: str = Field(default="")  # optional during draft authoring
    difficulty: Difficulty
    schema_sql: str = Field(..., min_length=1)
    sample_data_sql: str = Field(..., min_length=1)
    # Optional: the wizard creates a draft with no tasks; bulk callers may still pass tasks.
    tasks: Optional[List[SqlLabTaskCreate]] = None


class SqlLabTaskShellCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")  # prompt filled in progressively during authoring


class SqlLabTaskUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=255)  # may be cleared while drafting
    description: Optional[str] = None  # None = leave unchanged; "" = clear the prompt


class SqlLabTaskAssign(BaseModel):
    query: str = Field(..., min_length=1)


class SqlLabReorderRequest(BaseModel):
    ordered_ids: List[int] = Field(..., min_length=1)


class SqlLabMetaUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    difficulty: Optional[Difficulty] = None


class SqlLabSeedUpdate(BaseModel):
    schema_sql: str = Field(..., min_length=1)
    sample_data_sql: str = Field(..., min_length=1)


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
    status: str
    schema_sql: str
    sample_data_sql: str
    created_by: int
    created_at: datetime
    tasks: List[SqlLabTaskView]


class SqlLabQuestionListItem(BaseModel):
    id: int
    title: str
    difficulty: str
    status: str
    task_count: int
    created_by: int
    created_at: datetime


class SqlLabPracticeSubmit(BaseModel):
    """Submit a task answer while solving a SQL-lab question standalone (outside a lab)."""
    query: str = Field(..., min_length=1)
    task_id: int
