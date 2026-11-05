"""Request/response shapes of the RA API (mirrored in frontend/src/types/ra.types.ts)."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

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


class NotationIn(BaseModel):
    program: str = Field(..., max_length=MAX_PROGRAM_CHARS)
    # The schema's relation and attribute names, so names containing "-" read as one name.
    names: List[str] = Field(default_factory=list, max_length=2000)


class NotationLineOut(BaseModel):
    line: Optional[int] = None
    name: Optional[str] = None
    latex: str


class NotationOut(BaseModel):
    """An answer in textbook notation (LaTeX), one entry per statement, or why it can't be read."""
    ok: bool
    lines: List[NotationLineOut] = []
    error: Optional[RAErrorOut] = None


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
    proof: Optional[str] = None          # staff only: how the proof went (whole | by_parts | search | why not)


class SurvivingMutantOut(BaseModel):
    description: str
    line: Optional[int] = None
    text: str
    # The prover's view of a variant the test databases didn't catch: True = proved
    # equivalent (fine), False = proved different (the tests are too weak), None = undecided.
    equivalent: Optional[bool] = None


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


MAX_PARTS = 20

# How students answer (core/ra/answer_format.py), chosen by staff for the whole question.
AnswerFormat = Literal["mixed", "final_answer", "multi_step"]


class RAStepIn(BaseModel):
    """One step of a multi-step part; the last one is the final answer (its name is ignored)."""
    name: Optional[str] = Field(None, max_length=32)       # R1, R2 … (later steps use it)
    prompt: str = Field("", max_length=300)                # shown to students above the box
    marks: int = Field(0, ge=0, le=100)
    model_answer: str = Field("", max_length=MAX_PROGRAM_CHARS)


class RAStepOut(BaseModel):
    """A step as students see it (never its model answer)."""
    name: Optional[str] = None
    prompt: str
    marks: int


class RAStepStaffOut(RAStepOut):
    model_answer: str


class RAPartIn(BaseModel):
    """One part of a question: (i), (ii), … A question with one part needs no label or text."""
    id: Optional[int] = None                               # an existing part (keeps its attempts)
    label: str = Field("", max_length=50)                  # e.g. "(i)"
    description: str = Field("", max_length=20_000)       # markdown, shown to students
    marks: int = Field(1, ge=1, le=100)                    # what the part earns (multi-step: the steps' total)
    # Multi-step parts send ``steps`` instead; their model answer is built from them.
    model_answer: str = Field("", max_length=MAX_PROGRAM_CHARS)
    checkpoints: Optional[List[CheckpointIn]] = None       # None = every step of the model answer
    steps: Optional[List[RAStepIn]] = Field(None, max_length=20)


class RAQuestionIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=20_000)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    schema_sql: str = Field(..., min_length=1, max_length=MAX_SQL_CHARS)
    data_sql: str = Field("", max_length=MAX_SQL_CHARS)
    # With data_sql empty: the example data shown in the form (None = keep or build it).
    example_data_sql: Optional[str] = Field(None, max_length=MAX_SQL_CHARS)
    parts: List[RAPartIn] = Field(..., min_length=1, max_length=MAX_PARTS)
    answer_format: AnswerFormat = "mixed"
    show_step_direction: bool = True
    assessment_step_direction: bool = False    # the same, when the question is in an assessment
    compare_bags: bool = False
    hide_correctness: bool = False
    is_published: bool = False


class RAQuestionValidateIn(BaseModel):
    schema_sql: str = Field(..., min_length=1, max_length=MAX_SQL_CHARS)
    data_sql: str = Field("", max_length=MAX_SQL_CHARS)
    model_answer: str = Field("", max_length=MAX_PROGRAM_CHARS)
    # The question's type; a multi-step part sends its steps instead of a model answer.
    answer_format: AnswerFormat = "mixed"
    steps: Optional[List[RAStepIn]] = Field(None, max_length=20)
    checkpoints: Optional[List[CheckpointIn]] = None
    compare_bags: bool = False
    # With data_sql empty: the example data shown in the form, to run the model answer on.
    example_data_sql: Optional[str] = Field(None, max_length=MAX_SQL_CHARS)


class RAQuestionValidateOut(BaseModel):
    """Is the question valid, and how strong are its generated test databases?"""
    ok: bool
    error_source: Optional[Literal["schema", "data", "model_answer", "checkpoints", "steps"]] = None
    error: Optional[RAErrorOut] = None
    error_step: Optional[int] = None                        # which step, for a multi-step part
    relations: List[RelationOut] = []
    suite: Optional[SuiteSummaryOut] = None
    # The model answer's steps on the question's data, its example data, or else a generated test database.
    model_result: Optional[EvalOut] = None
    model_result_source: Optional[Literal["sample", "example", "generated"]] = None
    checkpoints: List[CheckpointIn] = []                    # the effective checkpoints


class RASchemaTextIn(BaseModel):
    """A schema written as text, e.g. ``STUDENT(*Sid, Sname, GPA)``, one relation per line."""
    text: str = Field(..., min_length=1, max_length=MAX_SQL_CHARS)
    link_keys: bool = True


class RASchemaTextOut(BaseModel):
    ok: bool
    schema_sql: str = ""
    relations: List[RelationOut] = []
    error: Optional[RAErrorOut] = None


class RAExampleDataIn(BaseModel):
    """Build example data for a question with no data of its own (staff form)."""
    schema_sql: str = Field(..., min_length=1, max_length=MAX_SQL_CHARS)
    model_answers: List[str] = Field([], max_length=MAX_PARTS)
    variant: int = Field(0, ge=0)                          # another one: the Regenerate button
    # The form's current example data: returned as it is if the schema still accepts it.
    current: Optional[str] = Field(None, max_length=MAX_SQL_CHARS)


class RAExampleDataOut(BaseModel):
    ok: bool
    data_sql: str = ""
    relations: List[RelationOut] = []
    error: Optional[RAErrorOut] = None


class RAQuestionListItem(BaseModel):
    id: int
    title: str
    difficulty: str
    is_published: bool
    has_data: bool
    attempts: int = 0
    solved: bool = False                     # every part solved
    parts_total: int = 1
    parts_solved: int = 0
    # For the staff Problems list (Created column, "Author: mine") and its ordering.
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None


class RAPartOut(BaseModel):
    """A part as students see it (never its model answer)."""
    id: int
    label: str
    description: str
    marks: int
    attempts: int = 0
    solved: bool = False
    submissions_used: int = 0                # Submits to this part (capped in assessments)
    steps: Optional[List[RAStepOut]] = None  # multi-step questions: one box per step


class RAPartStaffOut(RAPartOut):
    model_answer: str
    checkpoints: Optional[List[CheckpointIn]] = None
    suite: Optional[SuiteSummaryOut] = None
    steps: Optional[List[RAStepStaffOut]] = None


class RAQuestionOut(BaseModel):
    """What a student sees. Never the model answer, its steps or the test databases."""
    id: int
    title: str
    description: str
    difficulty: str
    relations: List[RelationOut]
    has_data: bool                           # the question has data of its own
    # Where the tuples in ``relations`` come from: the question's data, or its example data.
    data_source: Optional[Literal["sample", "example"]] = None
    answer_format: AnswerFormat = "mixed"     # how the question asks for its answer
    show_step_direction: bool
    hide_correctness: bool
    attempts: int = 0
    solved: bool = False                     # every part solved
    parts: List[RAPartOut] = []
    # Set when this is an assessment's copy of a question.
    assessment_id: Optional[int] = None
    max_submissions: Optional[int] = None    # per part; None = unlimited


class RAQuestionStaffOut(RAQuestionOut):
    schema_sql: str
    data_sql: str
    example_data_sql: Optional[str] = None   # what students see when data_sql is empty
    parts: List[RAPartStaffOut] = []
    compare_bags: bool
    is_published: bool
    assessment_step_direction: bool = False
    has_attempts: bool = False               # answered already: the type can't change any more


class RAAnswerIn(BaseModel):
    """One answer to one part: ``answer``, or for a multi-step question ``step_answers``
    (one per step, in order; empty ones allowed)."""
    answer: Optional[str] = Field(None, max_length=MAX_PROGRAM_CHARS)
    step_answers: Optional[List[str]] = Field(None, max_length=20)
    part_id: Optional[int] = None            # may be left out when the question has one part

    @model_validator(mode="after")
    def _one_answer(self):
        if self.step_answers is not None:
            if any(len(a) > MAX_PROGRAM_CHARS for a in self.step_answers):
                raise ValueError(f"A step is too long (max {MAX_PROGRAM_CHARS} characters).")
        elif not (self.answer or "").strip():
            raise ValueError("Write an answer first.")
        return self


class RABoxCheckOut(BaseModel):
    """One box of a multi-step answer, run on the shown data."""
    status: Literal["empty", "error", "ok"]
    error: Optional[RAErrorOut] = None
    step: Optional[Dict[str, Any]] = None    # {name, tree}, as in EvalOut.steps


class RACheckOut(BaseModel):
    """An answer evaluated step by step, not graded and not recorded."""
    ok: bool
    error: Optional[RAErrorOut] = None
    result: Optional[EvalOut] = None
    source: Optional[Literal["sample", "example", "generated"]] = None
    relations: List[RelationOut] = []
    boxes: Optional[List[RABoxCheckOut]] = None   # multi-step questions, instead of ``result``


class ShownResultOut(BaseModel):
    """After Submit: the student's result and the model answer's on the data shown with the
    question. ``student_extra[i]``: row i of the student's result shouldn't be there;
    ``expected_missing[i]``: row i of the model answer's result is missing from theirs."""
    source: Literal["sample", "example"]
    same_columns: bool
    equal: bool
    student: Dict[str, Any]
    expected: Dict[str, Any]
    student_extra: List[bool] = []
    expected_missing: List[bool] = []


class StepResultOut(BaseModel):
    """One step of a multi-step answer after Submit (services/ra/multi_step.py)."""
    index: int
    name: Optional[str] = None
    prompt: str
    marks: int
    earned: int
    # full: the final answer is correct · reached: a box computes this step ·
    # carried: a box computes it given the model's earlier steps · missed
    status: Literal["full", "reached", "carried", "missed"]
    credited_by: Optional[int] = None        # the box that earned it (0-based)
    box_status: Literal["empty", "error", "ok"]
    box_error: Optional[RAErrorOut] = None
    feedback: Optional[StepFeedbackOut] = None    # ✓/◐/○ for this box (status "none" when hidden)
    structure: Optional[Dict[str, Any]] = None    # the box evaluated on the shown data: {name, tree}
    student: Optional[Dict[str, Any]] = None      # for a missed step: the box's table on the shown data…
    expected: Optional[Dict[str, Any]] = None     # …and the model step's


class StepMarkingOut(BaseModel):
    earned: int
    total: int
    final_correct: bool
    source: Optional[Literal["sample", "example", "generated"]] = None   # where the tables come from
    steps: List[StepResultOut]


class RASubmitOut(BaseModel):
    attempt_id: int
    part_id: int
    max_submissions: Optional[int] = None
    submissions_used: int = 0
    # None when the question hides correctness: the student only learns it was submitted.
    grade: Optional[GradeOut] = None
    structure: Optional[EvalOut] = None
    structure_source: Optional[Literal["sample", "example", "generated"]] = None
    # Only with ``grade`` (it shows the model answer's result on the data the student sees).
    shown: Optional[ShownResultOut] = None
    # Multi-step questions, only with ``grade``: the marks of each step.
    marking: Optional[StepMarkingOut] = None


class RAAttemptOut(BaseModel):
    id: int
    part_id: Optional[int] = None
    answer: str
    verdict: Optional[str] = None        # None when the question hides correctness
    is_correct: Optional[bool] = None
    created_at: Any
    step_answers: Optional[List[str]] = None   # multi-step questions: the boxes
    marks_earned: Optional[int] = None         # multi-step questions (None when correctness is hidden)


class RAConvertPartIn(BaseModel):
    model_answer: str = Field("", max_length=MAX_PROGRAM_CHARS)
    checkpoints: Optional[List[CheckpointIn]] = None
    steps: Optional[List[RAStepIn]] = Field(None, max_length=20)
    marks: int = Field(1, ge=0, le=1000)


class RAFormatConvertIn(BaseModel):
    """The staff form's type switch: rewrite every part for the new type (nothing saved)."""
    schema_sql: str = Field(..., min_length=1, max_length=MAX_SQL_CHARS)
    from_format: AnswerFormat
    to_format: AnswerFormat
    parts: List[RAConvertPartIn] = Field(..., max_length=MAX_PARTS)


class RAConvertPartOut(BaseModel):
    model_answer: str
    checkpoints: Optional[List[CheckpointIn]] = None
    steps: Optional[List[RAStepStaffOut]] = None
    marks: int
    error: Optional[str] = None              # couldn't convert: rewrite it by hand


class RAFormatConvertOut(BaseModel):
    ok: bool
    error: Optional[RAErrorOut] = None       # the schema can't be read
    parts: List[RAConvertPartOut] = []


class RATryStepsIn(BaseModel):
    """The staff form's preview: mark a multi-step answer against draft steps (nothing saved)."""
    schema_sql: str = Field(..., min_length=1, max_length=MAX_SQL_CHARS)
    data_sql: str = Field("", max_length=MAX_SQL_CHARS)
    example_data_sql: Optional[str] = Field(None, max_length=MAX_SQL_CHARS)
    compare_bags: bool = False
    steps: List[RAStepIn] = Field(..., max_length=20)
    step_answers: List[str] = Field(..., max_length=20)


class RATryStepsOut(BaseModel):
    ok: bool
    error_source: Optional[Literal["schema", "data", "steps"]] = None
    error: Optional[RAErrorOut] = None
    error_step: Optional[int] = None
    grade: Optional[GradeOut] = None
    marking: Optional[StepMarkingOut] = None


PlaygroundGradeIn.model_rebuild()
