from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from enum import Enum


class AssessmentItemType(str, Enum):
    sql_question = "sql_question"
    er_question = "er_question"
    sql_lab = "sql_lab"
    graph_lab = "graph_lab"


class AssessmentItemIn(BaseModel):
    item_type: AssessmentItemType
    item_id: int
    order_index: int = 0


class AssessmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    items: List[AssessmentItemIn] = []
    password: Optional[str] = None


class AssessmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    items: Optional[List[AssessmentItemIn]] = None
    password: Optional[str] = None
    clear_password: bool = False


class AssessmentItemResponse(BaseModel):
    id: int
    item_type: AssessmentItemType
    item_id: int
    order_index: int
    item_title: str

    class Config:
        from_attributes = True


class AssessmentListItem(BaseModel):
    id: int
    title: str
    description: Optional[str]
    is_published: bool
    is_running: bool
    item_count: int
    has_password: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class AssessmentResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    is_published: bool
    is_running: bool
    items: List[AssessmentItemResponse]
    created_by: int
    password: Optional[str]
    has_password: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class AssessmentStudentRow(BaseModel):
    user_id: int
    email: str
    is_active: bool
    joined_at: datetime
    submitted_at: Optional[datetime]


class AssessmentStudentsResponse(BaseModel):
    assessment_id: int
    assessment_title: str
    students: List[AssessmentStudentRow]


class AssessmentItemComponentScore(BaseModel):
    assessment_item_id: int
    item_type: str
    item_id: int
    item_title: str
    order_index: int
    has_correct_attempt: Optional[bool] = None
    attempt_count: Optional[int] = None
    tasks_correct: Optional[int] = None
    tasks_total: Optional[int] = None
    visited: Optional[bool] = None


class StudentComponentScoresResponse(BaseModel):
    student_id: int
    student_email: str
    assessment_id: int
    assessment_title: str
    items: List[AssessmentItemComponentScore]
