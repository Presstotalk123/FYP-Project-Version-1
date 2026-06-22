from datetime import datetime
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

DifficultyLabel = Literal["Easy", "Medium", "Hard"]
ERNotation = Literal["Chen"]


# ----- Lab -----

class ErLabCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    join_password: str = Field(..., min_length=4, max_length=64)


class ErLabUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    join_password: Optional[str] = Field(None, min_length=4, max_length=64)


class ErLabResponse(BaseModel):
    id: int
    title: str
    description: str
    is_published: bool
    is_running: bool
    created_at: datetime
    updated_at: datetime


class ErLabStaffDetail(ErLabResponse):
    """Includes the plaintext join code; staff-only."""
    join_password: str


# ----- Question -----

class ErLabQuestionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    problem_statement: str = Field(..., min_length=1)
    notation: ERNotation = "Chen"
    difficulty_label: DifficultyLabel
    difficulty_rationale: str = Field(..., min_length=1)
    rubric_md: str = Field(..., min_length=1)
    rubric_json: dict[str, Any] = Field(default_factory=dict)
    instruction_history: list[str] = Field(default_factory=list)
    model_answer_storage_key: Optional[str] = None
    model_answer_url: Optional[str] = None
    order_index: int = 0
    show_rubric_on_attempt: bool = False


class ErLabQuestionUpdate(BaseModel):
    title: Optional[str] = None
    problem_statement: Optional[str] = None
    difficulty_label: Optional[DifficultyLabel] = None
    difficulty_rationale: Optional[str] = None
    rubric_md: Optional[str] = None
    rubric_json: Optional[dict[str, Any]] = None
    instruction_history: Optional[list[str]] = None
    order_index: Optional[int] = None
    model_answer_storage_key: Optional[str] = None
    model_answer_url: Optional[str] = None
    show_rubric_on_attempt: Optional[bool] = None


class ErLabQuestionResponse(BaseModel):
    id: int
    er_lab_id: int
    order_index: int
    title: str
    problem_statement: str
    notation: ERNotation
    difficulty_label: DifficultyLabel
    difficulty_rationale: str
    rubric_md: Optional[str] = None
    rubric_json: Optional[dict[str, Any]] = None
    instruction_history: list[str]
    model_answer_storage_key: Optional[str] = None
    model_answer_url: Optional[str] = None
    show_rubric_on_attempt: bool
    created_by: int
    created_at: datetime
    updated_at: datetime


# ----- Session -----

class ErLabSessionStart(BaseModel):
    join_password: str = ""


class ErLabSessionResponse(BaseModel):
    id: int
    er_lab_id: int
    user_id: int
    is_active: bool
    started_at: datetime
    ended_at: Optional[datetime] = None


# ----- Submission -----

class ErLabSubmissionResponse(BaseModel):
    id: int
    er_lab_question_id: int
    er_lab_id: int
    user_id: int
    session_id: int
    submitted_xml: Optional[str] = None
    submitted_image_storage_key: Optional[str] = None
    auto_score_earned: float
    auto_score_total: float
    auto_score_percent: float
    auto_score_label: str
    auto_checks_json: dict[str, Any] | list[Any] | str
    auto_graded_at: datetime
    override_score_earned: Optional[float] = None
    override_score_total: Optional[float] = None
    override_score_percent: Optional[float] = None
    override_reason: Optional[str] = None
    overridden_by: Optional[int] = None
    overridden_at: Optional[datetime] = None
    submitted_at: datetime


# ----- Scoring reads -----

class ErLabQuestionBestScore(BaseModel):
    er_lab_question_id: int
    best_percent: Optional[float] = None  # None when not attempted
    best_earned: Optional[float] = None
    best_total: Optional[float] = None
    attempts: int
    last_attempted_at: Optional[datetime] = None


class ErLabMyScoresResponse(BaseModel):
    er_lab_id: int
    user_id: int
    questions: list[ErLabQuestionBestScore]
    total_earned: float
    total_total: float


class ErLabStudentSummary(BaseModel):
    user_id: int
    email: str
    total_earned: float
    total_total: float
    attempts: int
    last_submission_at: Optional[datetime] = None


class ErLabStudentsResponse(BaseModel):
    er_lab_id: int
    lab_title: str
    total_questions: int
    students: list[ErLabStudentSummary]


# ----- Override -----

class ErLabOverrideRequest(BaseModel):
    score_earned: float = Field(..., ge=0)
    score_total: float = Field(..., gt=0)
    reason: str = Field(..., min_length=1, max_length=2000)
