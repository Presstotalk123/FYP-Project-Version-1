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


class ClassWindowIn(BaseModel):
    """One per-class-group access window in a Timing-Gateway save payload."""
    class_group: str = Field(..., min_length=1, max_length=100)
    start_at: datetime
    end_at: datetime
    is_enabled: bool = True

    @model_validator(mode="after")
    def _check_bounds(self):
        if self.end_at <= self.start_at:
            raise ValueError(
                f"End time must be after start time for class group '{self.class_group}'."
            )
        return self


class GatewayConfigUpdate(BaseModel):
    """Full replace of an assessment's Timing-Gateway configuration."""
    gateway_enabled: bool = False
    windows: List[ClassWindowIn] = []

    @model_validator(mode="after")
    def _check_unique_groups(self):
        groups = [w.class_group for w in self.windows]
        if len(groups) != len(set(groups)):
            raise ValueError("Each class group may have at most one window.")
        return self


class ClassWindowOut(BaseModel):
    id: int
    class_group: str
    start_at: datetime
    end_at: datetime
    is_enabled: bool
    # Computed lifecycle relative to server time: upcoming | active | completed.
    status: str
    # Count of students currently mid-attempt in this group's window (for edit warnings).
    active_session_count: int = 0

    class Config:
        from_attributes = True


class GatewayConfigResponse(BaseModel):
    assessment_id: int
    gateway_enabled: bool
    windows: List[ClassWindowOut]
    # Non-fatal warnings surfaced after a save (e.g. edited a window with active sessions).
    warnings: List[str] = []


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
    # Timing Gateway master toggle — when true, access is driven by per-class-group windows.
    gateway_enabled: bool = False
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
    # Timing Gateway master toggle — when true, access is driven by per-class-group windows.
    gateway_enabled: bool = False
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class AssessmentStudentRow(BaseModel):
    user_id: int
    email: str
    # Display name from the user record; None when the student never set one.
    name: Optional[str] = None
    class_group: Optional[str] = None
    is_active: bool
    joined_at: datetime
    submitted_at: Optional[datetime]
    # Weighted total (0-100) from the student's activity; None if the assessment is unweighted.
    weighted_score: Optional[float] = None


class AssessmentStudentsResponse(BaseModel):
    assessment_id: int
    assessment_title: str
    students: List[AssessmentStudentRow]


class StudentLabTaskResult(BaseModel):
    """Whether one specific lab task was solved by one specific student. The
    per-student counterpart to LabTaskAggregateScore (which is a cohort rate)."""
    task_id: int
    task_title: str
    order_index: int
    correct: bool


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
    # Lab items only: per-task ✓/✗ for this student. None for non-lab items and for
    # endpoints that don't populate it (kept optional so the existing staff
    # component-scores response is unchanged).
    tasks: Optional[List[StudentLabTaskResult]] = None


class StudentComponentScoresResponse(BaseModel):
    student_id: int
    student_email: str
    assessment_id: int
    assessment_title: str
    items: List[AssessmentItemComponentScore]
    # Weighted total (0-100); None if the assessment is unweighted (all weights 0).
    total_weighted_score: Optional[float] = None


class LabTaskAggregateScore(BaseModel):
    task_id: int
    task_title: str
    order_index: int
    # % of the roster who solved this specific task (0-100); None if the roster is empty.
    success_rate: Optional[float] = None
    # Headcounts behind success_rate: students who solved it, students who submitted at
    # least once, and every submission they made. success_rate is correct_count/roster,
    # so correct_count <= attempted_count <= the roster size.
    correct_count: int = 0
    attempted_count: int = 0
    total_attempts: int = 0


class AssessmentItemAggregateScore(BaseModel):
    assessment_item_id: int
    item_type: str
    item_id: int
    item_title: str
    order_index: int
    weight: int = 0
    # Mean correctness fraction (0.0-1.0) across the roster; None if the roster is empty.
    avg_score_fraction: Optional[float] = None
    # weight * avg_score_fraction — this item's average contribution to the weighted total.
    avg_weighted_points: Optional[float] = None
    # Lab items only: mean distinct-correct-tasks per student, and the lab's total task count.
    avg_tasks_correct: Optional[float] = None
    tasks_total: Optional[int] = None
    # Lab items only: per-task success rate across the roster.
    tasks: Optional[List[LabTaskAggregateScore]] = None

    # --- Headcounts (the counts behind avg_score_fraction) -----------------------
    # Students who got this item fully right. "Fully" is per type: a correct attempt
    # (sql_question), every non-deleted task solved (labs), a "pass" grade (er_question) —
    # so an ER item scoring 60% counts as attempted but not correct.
    correct_count: int = 0
    # Students who submitted at least once, and the total submissions across the roster.
    # ER attempts are read from er_submissions, which only the LangGraph engine writes:
    # under ERD_TUTOR_ENGINE=dify these stay 0 even though scores exist.
    attempted_count: int = 0
    total_attempts: int = 0
    # Mean attempts among the students who attempted (not the whole roster) — None when
    # nobody attempted, so the UI shows "—" rather than a misleading 0.
    avg_attempts: Optional[float] = None


class AssessmentItemAnalyticsResponse(BaseModel):
    assessment_id: int
    assessment_title: str
    # None when unfiltered (cohort-wide); set to the selected class_group otherwise.
    class_group: Optional[str] = None
    student_count: int
    # Students expected to sit this assessment (whitelist ∪ users), narrowed to class_group
    # when one is selected. The shared denominator for every item's attempted_count — it is
    # identical for all items, so it is not repeated per item.
    registered_count: int = 0
    # Mean weighted total (0-100) across the roster; None if unweighted or roster is empty.
    avg_weighted_score: Optional[float] = None
    # Distinct class groups present in THIS assessment's roster, for the group filter. Sent
    # here so the dashboard doesn't have to fetch the entire student roster just to populate
    # a dropdown, and so the options stay scoped to this assessment rather than the platform.
    class_groups: List[str] = []
    items: List[AssessmentItemAggregateScore]


class AssessmentAnalyticsSummaryRow(BaseModel):
    """One assessment's headline numbers for the admin dashboard index."""
    assessment_id: int
    title: str
    is_published: bool
    question_count: int
    # Students expected to sit it (whitelist ∪ users), scoped by the gateway's class groups.
    registered_count: int
    # Students who opened it — a session exists. Not the same as having attempted anything.
    started_count: int
    # Mean weighted total (0-100); None if the assessment is unweighted or nobody started.
    avg_weighted_score: Optional[float] = None


class AssessmentAnalyticsSummaryResponse(BaseModel):
    # Platform-wide, unscoped by class group — feeds the Overview tab's metric card. Served
    # here because /whitelist is admin-only while this dashboard is staff + admin.
    platform_registered: int
    platform_signed_in: int
    assessments: List[AssessmentAnalyticsSummaryRow]


class ItemStudentRow(BaseModel):
    """One student's outcome on one assessment question."""
    email: str
    name: Optional[str] = None
    class_group: Optional[str] = None
    # not_started (registered, never opened the assessment) | not_attempted (opened it,
    # never submitted for this question) | graded (submitted at least once).
    status: str
    # 0-100. None only when status is not_started — that student has no data at all,
    # which is different from scoring zero.
    score_percent: Optional[float] = None
    # Context beside the percent: "3/4 tasks", "Correct", "Incorrect". None for ER items,
    # whose percent is already the whole story.
    detail: Optional[str] = None
    attempts: int = 0


class ItemStudentsResponse(BaseModel):
    assessment_id: int
    assessment_item_id: int
    item_title: str
    item_type: str
    class_group: Optional[str] = None
    registered_count: int
    # Sorted weakest-first: non-starters, then ascending percent, ties broken by email.
    students: List[ItemStudentRow]
