from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

from app.schemas.assessment import AssessmentItemType


class StudentAssessmentListItem(BaseModel):
    id: int
    title: str
    description: Optional[str]
    is_running: bool
    has_password: bool

    class Config:
        from_attributes = True


class StudentAssessmentItemView(BaseModel):
    id: int
    item_type: AssessmentItemType
    item_id: int
    order_index: int
    item_title: str
    visited: bool

    class Config:
        from_attributes = True


class StudentAssessmentDetail(BaseModel):
    id: int
    title: str
    description: Optional[str]
    is_running: bool
    has_password: bool
    # True once this student has ended & submitted; the UI shows a "Completed" state
    # and hides the Join/Continue buttons (assessments are single-attempt).
    attempt_complete: bool = False
    items: List[StudentAssessmentItemView]

    class Config:
        from_attributes = True


class AssessmentSessionResponse(BaseModel):
    id: int
    assessment_id: int
    user_id: int
    is_active: bool
    joined_at: datetime
    submitted_at: Optional[datetime]

    class Config:
        from_attributes = True


class ItemVisitResponse(BaseModel):
    session_id: int
    assessment_item_id: int
    first_visited_at: datetime

    class Config:
        from_attributes = True
