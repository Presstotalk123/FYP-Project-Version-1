from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


GenerateRubricMode = Literal["create", "patch"]
DifficultyLabel = Literal["Easy", "Medium", "Hard"]
ERNotation = Literal["Chen"]


class DifficultyInfo(BaseModel):
    label: DifficultyLabel
    rationale: str = Field(..., min_length=1)


class GenerateRubricResponse(BaseModel):
    difficulty: DifficultyInfo
    rubric_json: dict[str, Any] = Field(default_factory=dict)
    rubric_md: str
    diff_summary: list[Any] = Field(default_factory=list)


class ERDiagramQuestionBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    problem_statement: str = Field(..., min_length=1)
    notation: ERNotation = "Chen"
    difficulty_label: DifficultyLabel
    difficulty_rationale: str = Field(..., min_length=1)
    rubric_md: str = Field(..., min_length=1)
    rubric_json: dict[str, Any] = Field(default_factory=dict)
    instruction_history: list[str] = Field(default_factory=list)


class ERDiagramQuestionCreate(ERDiagramQuestionBase):
    model_answer_storage_key: str | None = None
    model_answer_url: str | None = None


class ERDiagramQuestionResponse(ERDiagramQuestionBase):
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
    problem_statement: str
    difficulty_label: DifficultyLabel
    created_at: datetime

    class Config:
        from_attributes = True
