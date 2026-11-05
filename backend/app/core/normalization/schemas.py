from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FunctionalDependencyInput(BaseModel):
    lhs: list[str] = Field(min_length=1)
    rhs: list[str] = Field(min_length=1)


class RelationInput(BaseModel):
    name: str = Field(min_length=1)
    attributes: list[str] = Field(min_length=1)
    primary_key: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def key_belongs_to_relation(self) -> "RelationInput":
        if len(self.attributes) != len(set(self.attributes)):
            raise ValueError("A relation cannot contain duplicate attributes.")
        if len(self.primary_key) != len(set(self.primary_key)):
            raise ValueError("A primary key cannot contain duplicate attributes.")
        unknown = set(self.primary_key) - set(self.attributes)
        if unknown:
            raise ValueError(f"Primary-key attributes are not in the relation: {sorted(unknown)}")
        return self


class SubmissionInput(BaseModel):
    exercise_id: str = "course-registration-bcnf"
    target_normal_form: Literal["3NF", "BCNF"] = "BCNF"
    assumptions: str = ""
    functional_dependencies: list[FunctionalDependencyInput]
    relations: list[RelationInput]


class RelationEvaluation(BaseModel):
    name: str
    candidate_keys: list[list[str]]
    prime_attributes: list[str]
    satisfies_target: bool
    violations: list[str]
    proposed_primary_key: list[str] = Field(default_factory=list)
    proposed_key_is_candidate: bool = False


class SubmissionEvaluation(BaseModel):
    submission_id: str
    engine_version: str = "legacy"
    target_normal_form: Literal["3NF", "BCNF"]
    attribute_coverage: bool
    missing_attributes: list[str]
    lossless_join: bool
    dependency_preservation: bool
    unpreserved_dependencies: list[str]
    relations_satisfy_target: bool
    relation_results: list[RelationEvaluation]
    dependency_preservation_required: bool = False
    proposed_keys_correct: bool = False
    meets_requirements: bool = False
    process_evaluation: NormalizationProcessEvaluation | None = None
    note: str


class ExerciseResponse(BaseModel):
    id: str
    title: str
    target_normal_form: Literal["3NF", "BCNF"]
    relation_name: str
    attributes: list[str]
    requirements: list[str]


class NormalizationExerciseResponse(BaseModel):
    id: str
    version: str
    title: str
    scenario: str
    target_normal_form: Literal["3NF", "BCNF"]
    relation_name: str
    attributes: list[str]
    functional_dependencies: list[FunctionalDependencyInput]
    requirements: list[str]
    dependency_preservation_required: bool
    workflow: Literal["recursive_decomposition", "synthesis"]
    source_fd_attempt_id: str | None = None


class StepRelationInput(RelationInput):
    node_id: str = Field(min_length=1)


class BCNFDecompositionStepInput(BaseModel):
    step_id: str = Field(min_length=1)
    parent_node_id: str = Field(min_length=1)
    selected_fd: FunctionalDependencyInput
    children: list[StepRelationInput] = Field(min_length=2, max_length=2)


class BCNFProcessInput(BaseModel):
    workflow: Literal["recursive_decomposition"]
    root: StepRelationInput
    steps: list[BCNFDecompositionStepInput] = Field(default_factory=list)


class SynthesisRelationJustificationInput(BaseModel):
    relation_name: str = Field(min_length=1)
    supporting_fds: list[FunctionalDependencyInput] = Field(min_length=1)


class ThreeNFProcessInput(BaseModel):
    workflow: Literal["synthesis"]
    proposed_minimal_cover: list[FunctionalDependencyInput] = Field(min_length=1)
    synthesis_relations: list[SynthesisRelationJustificationInput] = Field(min_length=1)


class NormalizationSubmissionInput(BaseModel):
    exercise_id: str
    exercise_version: str
    assumptions: str = Field(default="", max_length=1000)
    relations: list[RelationInput] = Field(min_length=1)
    process: BCNFProcessInput | ThreeNFProcessInput
    source_fd_attempt_id: str | None = None
    target_normal_form: Literal["3NF", "BCNF"] | None = None


class ClosureRequest(BaseModel):
    exercise_id: str
    exercise_version: str
    attributes: list[str] = Field(min_length=1)
    source_fd_attempt_id: str | None = None
    target_normal_form: Literal["3NF", "BCNF"] | None = None
    functional_dependencies: list[FunctionalDependencyInput] | None = None


class ClosureStepResponse(BaseModel):
    step: int
    lhs: list[str]
    rhs: list[str]
    introduced: list[str]
    closure: list[str]


class ClosureResponse(BaseModel):
    exercise_id: str
    exercise_version: str
    seed: list[str]
    closure: list[str]
    is_superkey: bool
    steps: list[ClosureStepResponse]


class NormalizationAnalysisResponse(BaseModel):
    exercise_id: str
    exercise_version: str
    candidate_keys: list[list[str]]
    prime_attributes: list[str]
    minimal_cover: list[FunctionalDependencyInput]


class ProcessStepEvaluation(BaseModel):
    step: str
    valid: bool
    feedback: str


class NormalizationProcessEvaluation(BaseModel):
    workflow: Literal["recursive_decomposition", "synthesis"]
    valid: bool
    step_results: list[ProcessStepEvaluation]
    errors: list[str]


class SubmissionHistoryItem(BaseModel):
    id: str
    created_at: datetime
    exercise_id: str = ""
    exercise_version: str = ""
    assumptions: str
    dependency_count: int
    relation_count: int
    relations: list[RelationInput] = Field(default_factory=list)
    process: BCNFProcessInput | ThreeNFProcessInput | None = None
    evaluation: SubmissionEvaluation


class BusinessStatementResponse(BaseModel):
    id: str
    text: str


class FDExerciseResponse(BaseModel):
    id: str
    version: str
    title: str
    difficulty: Literal["easy", "medium", "hard"]
    target_normal_forms: list[Literal["3NF", "BCNF"]] = Field(
        min_length=1, max_length=1
    )
    scenario: str
    relation_name: str
    attributes: list[str]
    statements: list[BusinessStatementResponse]
    sample_rows: list[dict[str, str]]


class QuestionSummaryResponse(BaseModel):
    id: str
    version: str
    title: str
    difficulty: Literal["easy", "medium", "hard"]
    relation_name: str
    attribute_count: int
    statement_count: int
    target_normal_forms: list[Literal["3NF", "BCNF"]] = Field(
        min_length=1, max_length=1
    )
    attempt_count: int = 0
    best_score: int | None = None


class FDSubmissionInput(BaseModel):
    exercise_id: str = "course-registration-fd"
    exercise_version: str
    functional_dependencies: list[FunctionalDependencyInput] = Field(min_length=1)
    assumption: str = Field(default="", max_length=1000)


class FDContradictionResponse(BaseModel):
    lhs: list[str]
    rhs: list[str]
    first_row: int
    second_row: int


class FDFormalEvidenceResponse(BaseModel):
    logically_equivalent: bool
    reference_coverage: float = Field(ge=0, le=1)
    submission_soundness: float = Field(ge=0, le=1)
    reference_matched: int = Field(ge=0)
    reference_total: int = Field(ge=1)
    submission_matched: int = Field(ge=0)
    submission_total: int = Field(ge=0)
    sample_contradictions: list[FDContradictionResponse]


class FDSemanticEvidenceResponse(BaseModel):
    verdict: Literal["accept", "reject", "staff_review"]
    provider: str
    model: str
    response_id: str


class FDSubmissionResult(BaseModel):
    attempt_id: str
    exercise_id: str
    exercise_version: str
    decision: Literal["accepted", "rejected", "staff_review"]
    decision_source: Literal[
        "deterministic_equivalence",
        "sample_contradiction",
        "trivial_only",
        "semantic_review",
        "semantic_review_disabled",
        "provider_failure",
    ]
    can_proceed: bool
    feedback: str
    formal_evidence: FDFormalEvidenceResponse
    semantic_evidence: FDSemanticEvidenceResponse | None = None


class FDAttemptHistoryItem(BaseModel):
    id: str
    created_at: datetime
    exercise_id: str
    exercise_version: str
    assumption: str
    functional_dependencies: list[FunctionalDependencyInput]
    result: FDSubmissionResult


class CanvasNodePosition(BaseModel):
    node_id: str = Field(min_length=1, max_length=128)
    x: float = Field(ge=-100_000, le=100_000)
    y: float = Field(ge=-100_000, le=100_000)


class IntegratedSubmissionInput(BaseModel):
    exercise_id: str = "course-registration-fd"
    exercise_version: str
    target_normal_form: Literal["3NF", "BCNF"]
    functional_dependencies: list[FunctionalDependencyInput] = Field(min_length=1)
    assumption: str = Field(default="", max_length=1000)
    relations: list[RelationInput] = Field(min_length=1)
    process: BCNFProcessInput
    canvas_positions: list[CanvasNodePosition] = Field(default_factory=list, max_length=100)


class IntegratedScoreResponse(BaseModel):
    fd_percent: int = Field(ge=0, le=100)
    normalization_percent: int = Field(ge=0, le=100)
    overall_percent: int = Field(ge=0, le=100)


class IntegratedSubmissionResult(BaseModel):
    submission_id: str
    decision: Literal["accepted", "rejected", "staff_review"]
    score: IntegratedScoreResponse
    fd_evaluation: FDSubmissionResult
    normalization_evaluation: SubmissionEvaluation


class IntegratedSubmissionHistoryItem(BaseModel):
    id: str
    created_at: datetime
    exercise_id: str
    exercise_version: str
    target_normal_form: Literal["3NF", "BCNF"]
    functional_dependencies: list[FunctionalDependencyInput]
    assumption: str
    relations: list[RelationInput]
    process: BCNFProcessInput
    canvas_positions: list[CanvasNodePosition] = Field(default_factory=list)
    result: IntegratedSubmissionResult
