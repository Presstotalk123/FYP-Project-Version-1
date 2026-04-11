from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


GenerateRubricMode = Literal["create", "patch"]
ERSubmissionMode = Literal["Query", "Submit"]
DifficultyLabel = Literal["Easy", "Medium", "Hard"]
ERNotation = Literal["Chen"]


class DifficultyInfo(BaseModel):
    label: DifficultyLabel
    rationale: str = Field(..., min_length=1)


class RubricDiffItem(BaseModel):
    section: str | None = None
    change: str | None = None
    details: dict[str, Any] | None = None


class GenerateRubricResponse(BaseModel):
    difficulty: DifficultyInfo
    rubric_json: dict[str, Any] = Field(default_factory=dict)
    rubric_md: str
    diff_summary: list[RubricDiffItem | str | dict[str, Any]] = Field(default_factory=list)


class ERSubmissionScore(BaseModel):
    model_config = ConfigDict(extra="allow")

    label: str = Field(..., min_length=1)
    earned_points: float
    total_points: float
    percent: float | str


class ERSubmissionCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    dimension: str = Field(..., min_length=1)
    requirement_level: Literal["must", "should", "optional", "not_applicable"]
    points: float
    status: Literal["pass", "fail", "partial", "not_applicable"]
    brief_reason: str = Field(..., min_length=1)


class ERSubmissionStructuredOutput(BaseModel):
    score: ERSubmissionScore
    student_message: str = Field(..., min_length=1)
    checks: list[ERSubmissionCheck]


class ERSubmissionResponse(BaseModel):
    mode: ERSubmissionMode
    text: str
    structured_output: ERSubmissionStructuredOutput | None = None


class ERDiagramQuestionBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    problem_statement: str = Field(..., min_length=1)
    notation: ERNotation = "Chen"
    difficulty_label: DifficultyLabel
    difficulty_rationale: str = Field(..., min_length=1)
    rubric_md: str = Field(..., min_length=1)
    rubric_json: dict[str, Any] = Field(default_factory=dict)
    instruction_history: list[str] = Field(default_factory=list)
    show_rubric_on_attempt: bool = False


class ERDiagramQuestionCreate(ERDiagramQuestionBase):
    model_answer_storage_key: str | None = None
    model_answer_url: str | None = None


class ERDiagramQuestionResponse(ERDiagramQuestionBase):
    rubric_md: str | None = None
    rubric_json: dict[str, Any] | None = None
    id: int
    model_answer_storage_key: str | None = None
    model_answer_url: str | None = None
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ERDiagramQuestionListItem(BaseModel):
    id: int
    title: str
    problem_statement: str = Field(..., max_length=200)
    difficulty_label: DifficultyLabel
    created_by: int
    created_by_role: Literal["student", "staff"]
    created_at: datetime

    class Config:
        from_attributes = True
