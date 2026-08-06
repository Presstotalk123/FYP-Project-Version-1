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
    # True once this student has ended & submitted this assessment (single-attempt).
    attempt_complete: bool = False
    # Overall weighted score (0-100). Populated only once staff have stopped the
    # assessment (results released); None while running or unweighted. Mirrors
    # StudentAssessmentDetail.weighted_score.
    weighted_score: Optional[float] = None
    # When the student submitted their attempt; None if not yet completed. Used by the
    # dashboard to order "recent" results and show a submission date.
    submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class StudentAssessmentItemView(BaseModel):
    id: int
    item_type: AssessmentItemType
    item_id: int
    order_index: int
    # Integer percentage (0-100) this question contributes to the assessment total.
    weight: int
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
    # Optional whole-minute time limit; None = untimed. Shown on the Begin screen.
    time_limit_minutes: Optional[int] = None
    # True once this student has ended & submitted; the UI shows a "Completed" state
    # and hides the Join/Continue buttons (assessments are single-attempt).
    attempt_complete: bool = False
    # Overall weighted score (0-100) for this student. Only populated once the assessment
    # has been stopped by staff (results released); None while the assessment is still
    # running or for unweighted/legacy assessments.
    weighted_score: Optional[float] = None
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
    # Deadline for this attempt; None = untimed. The frontend countdown ticks toward this.
    end_time: Optional[datetime] = None

    class Config:
        from_attributes = True


class ItemVisitResponse(BaseModel):
    session_id: int
    assessment_item_id: int
    first_visited_at: datetime

    class Config:
        from_attributes = True
