from typing import List, Literal, Optional
from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]

# ---- Submit: grade (JudgeResult) — DSL node "Submit LLM" ----
class JudgeCheck(BaseModel):
    id: str
    dimension: str
    requirement_level: Literal["must", "should", "optional"]
    points: float
    status: Literal["pass", "fail", "partial", "not_applicable"]
    brief_reason: str

class IBL(BaseModel):
    stage_used: Literal["orientation", "conceptualization", "investigation", "conclusion", "discussion"]
    next_stage: Literal["orientation", "conceptualization", "investigation", "conclusion", "discussion"]
    hint_level_used: int = Field(ge=1, le=4)
    next_hint_level: int = Field(ge=1, le=4)

class JudgeResult(BaseModel):
    checks: List[JudgeCheck]
    ibl: IBL
    student_message: str

# ---- Submit: deterministic score (SubmitResult) — DSL node "Parse & Calc grade" ----
class Score(BaseModel):
    earned_points: float
    total_points: float
    percent: int
    label: str  # "pass" | "partial" | "needs work"

class SubmitResult(BaseModel):
    score: Score
    top_issues: List[str]
    failed_must_checks: List[dict]
    progress: dict
    ibl: dict
    student_message: str
    checks: List[JudgeCheck]  # array of final checks, matching the Dify SSE contract

# ---- Query state update — DSL node "Query State Updater" ----
class QueryStateUpdate(BaseModel):
    next_ibl_stage: Literal["orientation", "conceptualization", "investigation", "conclusion", "discussion"]
    next_hint_level: int = Field(ge=1, le=4)
    last_student_goal: str
    misconceptions: List[str] = Field(max_length=3)
    query_summary: str

# ---- Observation (Extract ERD 1) and Canonical (Extract ERD 2) ----
# These mirror the two large DSL schemas. Implement field-for-field from the DSL
# `structured_output.schema` of nodes "Extract ERD 1" and "Extract ERD 2".
# (Full nested models below — entities/relationships/attributes/endpoints/etc.)
class _Entity(BaseModel):
    id: str; raw_name: str; normalized_name: str; evidence: str; confidence: Confidence

class _Relationship(BaseModel):
    id: str; raw_name: str; normalized_name: str
    participant_entity_ids: List[str]; evidence: str; confidence: Confidence

class _ObsAttribute(BaseModel):
    id: str; raw_name: str; normalized_name: str; owner_id: str
    owner_type: Literal["entity", "relationship", "unknown"]
    attribute_kind_observed: Literal["normal", "key", "unknown"]
    evidence: str; confidence: Confidence

class _Endpoint(BaseModel):
    relationship_id: str; entity_id: str
    observed_text_marker: str
    observed_endpoint_cue: Literal["sharp_arrowhead", "curved_arrowhead", "no_arrow_visible", "unknown"]
    evidence: str; confidence: Confidence

class _Uncertain(BaseModel):
    raw_text: str; suspected_type: str; possible_owner_ids: List[str]; reason: str; evidence: str

class _Unclassified(BaseModel):
    raw_text: str; evidence: str; reason: str

class ObservationJSON(BaseModel):
    source_mode: Literal["image"]
    stage: Literal["observation_extraction"]
    entities: List[_Entity]
    relationships: List[_Relationship]
    attributes: List[_ObsAttribute]
    relationship_endpoints: List[_Endpoint]
    uncertain_items: List[_Uncertain]
    unclassified_labels: List[_Unclassified]

class _CanonAttribute(BaseModel):
    id: str; raw_name: str; normalized_name: str; owner_id: str
    owner_type: Literal["entity", "relationship", "unknown"]
    attribute_kind: Literal["normal", "key", "multivalued", "derived", "composite_part", "unknown"]
    evidence: str; confidence: Confidence

class _Cardinality(BaseModel):
    relationship_id: str; entity_id: str; raw_marker: str
    normalized_cardinality: Literal["1", "N", "M", "0..1", "1..1", "0..N", "1..N", "unknown"]
    evidence: str; confidence: Confidence

class _Participation(BaseModel):
    relationship_id: str; entity_id: str
    participation_type: Literal["total", "partial", "unknown"]; evidence: str; confidence: Confidence

class _Audit(BaseModel):
    all_visible_labels_accounted_for: bool
    all_detected_entities_checked_for_attributes: bool
    all_detected_relationships_checked_for_participants: bool
    notes: List[str]

class CanonicalERD(BaseModel):
    source_mode: Literal["image", "xml"]
    target_notation: Literal["Chen"]
    entities: List[_Entity]
    relationships: List[_Relationship]
    attributes: List[_CanonAttribute]
    cardinalities: List[_Cardinality]
    participation: List[_Participation]
    uncertain_items: List[_Uncertain]
    unclassified_labels: List[_Unclassified]
    completeness_audit: _Audit
