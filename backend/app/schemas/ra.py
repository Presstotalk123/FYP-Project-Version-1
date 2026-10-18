"""Request/response shapes of the RA API (mirrored in frontend/src/types/ra.types.ts)."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.ra import RAError as EngineError
from app.core.ra.parser import MAX_PROGRAM_CHARS
from app.core.ra.schema import MAX_SQL_CHARS


class RAStatus(BaseModel):
    enabled: bool
    aggregate_nulls: str


class RAErrorOut(BaseModel):
    code: str
    message: str
    line: Optional[int] = None
    col: Optional[int] = None
    hint: Optional[str] = None

    @classmethod
    def from_engine(cls, e: EngineError) -> "RAErrorOut":
        return cls(**e.to_dict())


class RelationOut(BaseModel):
    name: str
    columns: List[str]
    types: List[str]
    primary_key: List[str]
    rows: List[List[Any]]


class EvalOut(BaseModel):
    """The evaluated answer plus every intermediate step (see core/ra/evaluator.py)."""
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    steps: List[Dict[str, Any]]
    warnings: List[RAErrorOut] = []


class PlaygroundRunIn(BaseModel):
    schema_sql: str = Field(..., max_length=MAX_SQL_CHARS)
    data_sql: str = Field("", max_length=MAX_SQL_CHARS)
    # Empty: only load the schema, so the page can show the relations before a run.
    expression: str = Field("", max_length=MAX_PROGRAM_CHARS)


class PlaygroundRunOut(BaseModel):
    ok: bool
    # Which input the error is in: the schema/data SQL, or the RA expression.
    error_source: Optional[Literal["schema", "expression"]] = None
    error: Optional[RAErrorOut] = None
    relations: List[RelationOut] = []
    result: Optional[EvalOut] = None
    elapsed_ms: float = 0


class GradingExampleOut(BaseModel):
    title: str
    model_answer: str
    answer: str


class ExampleOut(BaseModel):
    id: str
    title: str
    description: str
    schema_sql: str
    data_sql: str
    expressions: List[str]
    grading_examples: List[GradingExampleOut] = []


class StepFeedbackOut(BaseModel):
    """One statement of the student's answer compared with the model answer's steps."""
    name: Optional[str] = None
    line: Optional[int] = None
    text: str
    columns: List[str]
    status: Literal["match", "close", "none"]
    checkpoint: Optional[str] = None
    renamed: bool = False
    case: Optional[Dict[str, Any]] = None


class GradeOut(BaseModel):
    verdict: Literal["correct", "wrong_columns", "wrong_result", "wrong_in_general", "invalid_expression"]
    message: str
    method: Optional[Literal["proof", "tested", "sample"]] = None
    expected_columns: List[str] = []
    student_columns: List[str] = []
    databases_checked: int = 0
    missing_count: int = 0
    extra_count: int = 0
    extra_rows: List[List[Any]] = []
    counterexample: Optional[Dict[str, Any]] = None
    steps: List[StepFeedbackOut] = []
    error: Optional[RAErrorOut] = None
    elapsed_ms: float = 0


class SurvivingMutantOut(BaseModel):
    description: str
    line: Optional[int] = None
    text: str


class SuiteSummaryOut(BaseModel):
    """How strong the question's test databases are (see core/ra/suite.py)."""
    databases: int
    mutants: int
    mutants_killed: int
    candidates_tried: int
    build_ms: float
    surviving_mutants: List[SurvivingMutantOut] = []


class PlaygroundGradeIn(BaseModel):
    schema_sql: str = Field(..., max_length=MAX_SQL_CHARS)
    data_sql: str = Field("", max_length=MAX_SQL_CHARS)
    model_answer: str = Field(..., max_length=MAX_PROGRAM_CHARS)
    answer: str = Field(..., max_length=MAX_PROGRAM_CHARS)
    # As on a question (the staff form's test bench uses this endpoint).
    checkpoints: Optional[List["CheckpointIn"]] = None
    compare_bags: bool = False


class PlaygroundGradeOut(BaseModel):
    ok: bool
    # Which input an error is in. A student-answer error is a grade (invalid_expression), not this.
    error_source: Optional[Literal["schema", "model"]] = None
    error: Optional[RAErrorOut] = None
    grade: Optional[GradeOut] = None
    suite: Optional[SuiteSummaryOut] = None
    # The student's answer evaluated step by step, for "Show structure": on the question's
    # data if it has any, otherwise on one of the generated test databases.
    structure: Optional[EvalOut] = None
    structure_source: Optional[Literal["sample", "generated"]] = None
    structure_relations: List[RelationOut] = []


# ── RA questions ─────────────────────────────────────────────────────────────
class CheckpointIn(BaseModel):
    statement: Optional[str] = Field(None, max_length=64)   # a model step's name; None = the final answer
    label: str = Field(..., min_length=1, max_length=200)    # shown to students, e.g. "the CE courses"


class RAQuestionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=20_000)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    schema_sql: str = Field(..., min_length=1, max_length=MAX_SQL_CHARS)
    data_sql: str = Field("", max_length=MAX_SQL_CHARS)
    model_answer: str = Field(..., min_length=1, max_length=MAX_PROGRAM_CHARS)
    checkpoints: Optional[List[CheckpointIn]] = None       # None = every step of the model answer
    show_step_direction: bool = True
    assessment_step_direction: bool = False    # the same, when the question is in an assessment
    compare_bags: bool = False
    hide_correctness: bool = False
    is_published: bool = False


class RAQuestionValidateIn(BaseModel):
    schema_sql: str = Field(..., min_length=1, max_length=MAX_SQL_CHARS)
    data_sql: str = Field("", max_length=MAX_SQL_CHARS)
    model_answer: str = Field(..., min_length=1, max_length=MAX_PROGRAM_CHARS)
    checkpoints: Optional[List[CheckpointIn]] = None
    compare_bags: bool = False


class RAQuestionValidateOut(BaseModel):
    """Is the question valid, and how strong are its generated test databases?"""
    ok: bool
    error_source: Optional[Literal["schema", "data", "model_answer", "checkpoints"]] = None
    error: Optional[RAErrorOut] = None
    relations: List[RelationOut] = []
    suite: Optional[SuiteSummaryOut] = None
    # The model answer's steps on the question's data, or on a generated example database.
    model_result: Optional[EvalOut] = None
    model_result_source: Optional[Literal["sample", "generated"]] = None
    checkpoints: List[CheckpointIn] = []                    # the effective checkpoints


class RAQuestionListItem(BaseModel):
    id: int
    title: str
    difficulty: str
    is_published: bool
    has_data: bool
    attempts: int = 0
    solved: bool = False


class RAQuestionOut(BaseModel):
    """What a student sees. Never the model answer, its steps or the test databases."""
    id: int
    title: str
    description: str
    difficulty: str
    relations: List[RelationOut]
    has_data: bool
    show_step_direction: bool
    hide_correctness: bool
    attempts: int = 0
    solved: bool = False
    # Set when this is an assessment's copy of a question.
    assessment_id: Optional[int] = None
    max_submissions: Optional[int] = None    # None = unlimited
    submissions_used: int = 0


class RAQuestionStaffOut(RAQuestionOut):
    schema_sql: str
    data_sql: str
    model_answer: str
    checkpoints: Optional[List[CheckpointIn]] = None
    compare_bags: bool
    is_published: bool
    assessment_step_direction: bool = False
    suite: Optional[SuiteSummaryOut] = None


class RAAnswerIn(BaseModel):
    answer: str = Field(..., min_length=1, max_length=MAX_PROGRAM_CHARS)


class RACheckOut(BaseModel):
    """An answer evaluated step by step, not graded and not recorded."""
    ok: bool
    error: Optional[RAErrorOut] = None
    result: Optional[EvalOut] = None
    source: Optional[Literal["sample", "generated"]] = None
    relations: List[RelationOut] = []


class RASubmitOut(BaseModel):
    attempt_id: int
    max_submissions: Optional[int] = None
    submissions_used: int = 0
    # None when the question hides correctness: the student only learns it was submitted.
    grade: Optional[GradeOut] = None
    structure: Optional[EvalOut] = None
    structure_source: Optional[Literal["sample", "generated"]] = None


class RAAttemptOut(BaseModel):
    id: int
    answer: str
    verdict: Optional[str] = None        # None when the question hides correctness
    is_correct: Optional[bool] = None
    created_at: Any


PlaygroundGradeIn.model_rebuild()
