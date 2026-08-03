from pydantic import BaseModel, Field, model_validator
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
    # Integer percentage (0-100) of the assessment total. 0 on every item means
    # "unweighted" and the endpoint auto-distributes equally; otherwise the weights
    # across all items must total exactly 100 (see _validate_weight_total).
    weight: int = Field(0, ge=0, le=100)
    # Per-item override written onto the content clone at publish. When True, students
    # see a neutral "Submitted" result instead of Correct/Incorrect. Ignored for er_question.
    hide_correctness: bool = False
    # Per-item cap on how many queries a student may run on this SQL question during the
    # assessment. None = unlimited. Only meaningful for sql_question items.
    max_queries: Optional[int] = Field(None, ge=1)


def _validate_weight_total(items: Optional[List[AssessmentItemIn]]) -> None:
    """Enforce that per-question weights total exactly 100%.

    Empty item list -> nothing to weight. All-zero weights -> legacy/unweighted, left
    for the endpoint to auto-distribute. Any non-zero weight -> the full set must sum to 100.
    """
    if not items:
        return
    total = sum(i.weight for i in items)
    if total == 0:
        return
    if total != 100:
        raise ValueError(f"Question weightage must total 100% (currently {total}%)")


class AssessmentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    items: List[AssessmentItemIn] = []
    password: Optional[str] = None
    # Optional whole-minute time limit; None = untimed.
    time_limit_minutes: Optional[int] = Field(None, ge=1)

    @model_validator(mode="after")
    def _check_weights(self):
        _validate_weight_total(self.items)
        return self


class AssessmentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    items: Optional[List[AssessmentItemIn]] = None
    password: Optional[str] = None
    clear_password: bool = False
    # Whole-minute time limit. Send an explicit value to set it; send null with
    # clear_time_limit=True to remove it.
    time_limit_minutes: Optional[int] = Field(None, ge=1)
    clear_time_limit: bool = False

    @model_validator(mode="after")
    def _check_weights(self):
        if self.items is not None:
            _validate_weight_total(self.items)
        return self


class AssessmentItemResponse(BaseModel):
    id: int
    item_type: AssessmentItemType
    item_id: int
    order_index: int
    weight: int
    hide_correctness: bool
    # Per-item max queries cap for SQL questions; None = unlimited.
    max_queries: Optional[int] = None
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
    time_limit_minutes: Optional[int] = None
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
    time_limit_minutes: Optional[int] = None
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
    # Weighted total (0-100) from the student's activity; None if the assessment is unweighted.
    weighted_score: Optional[float] = None


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
    # Weightage (%) staff assigned to this question.
    weight: int = 0
    # Correctness fraction 0.0-1.0 for this item (binary for SQL, proportional for labs/ER).
    score_fraction: Optional[float] = None
    # weight * score_fraction — this item's contribution to the weighted total.
    weighted_points: Optional[float] = None


class StudentComponentScoresResponse(BaseModel):
    student_id: int
    student_email: str
    assessment_id: int
    assessment_title: str
    items: List[AssessmentItemComponentScore]
    # Weighted total (0-100); None if the assessment is unweighted (all weights 0).
    total_weighted_score: Optional[float] = None
