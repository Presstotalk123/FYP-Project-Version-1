from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class Difficulty(BaseModel):
    label: Literal["Easy", "Medium", "Hard"]
    rationale: str


class Meta(BaseModel):
    notation_target: str
    grading_goal: str
    version_hint: str
    assumptions: str


class Policy(BaseModel):
    naming_tolerance: str
    allow_equivalences: str
    cardinality_strictness: str
    ambiguity_handling: str


class CardinalityEndpoint(BaseModel):
    entity: str
    cardinality: str
    participation: Optional[str] = None


class Cardinality(BaseModel):
    relationship: str
    endpoints: List[CardinalityEndpoint] = Field(default_factory=list)
    relationship_attributes: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class KeysConstraint(BaseModel):
    entity: str
    primary_key: List[str] = Field(default_factory=list)
    other_constraints: List[str] = Field(default_factory=list)


class CanonicalTargets(BaseModel):
    entities: List[str] = Field(default_factory=list)
    relationships: List[str] = Field(default_factory=list)
    cardinalities: List[Cardinality] = Field(default_factory=list)
    keys_constraints: List[KeysConstraint] = Field(default_factory=list)


class DecisionPolicy(BaseModel):
    exact_name_required: bool
    semantic_alias_allowed: bool
    abbreviation_allowed: bool
    owner_must_match: bool
    ambiguous_label_policy: Literal["pass", "partial", "fail"]
    missing_policy: Literal["fail", "not_applicable"]
    explicit_diagram_evidence_required: bool
    unclear_evidence_policy: Literal["fail", "not_applicable"]
    partial_allowed: bool


class EquivalenceOption(BaseModel):
    type: str
    description: str


class TargetEndpoint(BaseModel):
    entity: Optional[str] = None
    cardinality: Optional[str] = None
    participation: Optional[str] = None
    expected_cardinality: Optional[str] = None
    expected_participation: Optional[str] = None


class KeysRequired(BaseModel):
    entity: str
    primary_key: Optional[str] = None


class Target(BaseModel):
    entity: Optional[str] = None
    entities: List[str] = Field(default_factory=list)
    attribute: Optional[str] = None
    attributes_required: List[str] = Field(default_factory=list)
    relationship: Optional[str] = None
    relationships_required: List[str] = Field(default_factory=list)
    participant: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    cardinality: Optional[str] = None
    endpoints: List[TargetEndpoint] = Field(default_factory=list)
    relationship_attributes_required: List[str] = Field(default_factory=list)
    keys_required: List[KeysRequired] = Field(default_factory=list)
    rule: Optional[str] = None
    description: Optional[str] = None
    label: Optional[str] = None
    note: Optional[str] = None


class Check(BaseModel):
    id: str
    dimension: Literal["entities", "attributes", "relationships", "cardinality",
                       "keys_constraints", "equivalences", "global"]
    type: str
    target: Target
    requirement_level: Literal["must", "should", "optional"]
    points: int = Field(ge=0)
    pass_criteria: str
    fail_reason_template: str
    evidence: Literal["diagram_llm_extraction", "either"]
    equivalence_options: List[EquivalenceOption] = Field(default_factory=list)
    notes: Optional[str] = None
    decision_policy: DecisionPolicy


class RubricJson(BaseModel):
    meta: Meta
    policy: Policy
    canonical_targets: CanonicalTargets
    checks: List[Check] = Field(default_factory=list)


class RubricGeneration(BaseModel):
    difficulty: Difficulty
    rubric_json: RubricJson
    rubric_md: str
    diff_summary: List[str] = Field(default_factory=list)
