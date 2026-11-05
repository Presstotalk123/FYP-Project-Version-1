"""Authoring schemas are private; student payloads use explicit allow lists."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Output(StrictModel):
    columns: list[str] = Field(max_length=30)
    rows: list[list[str | int | float | bool | None]] = Field(max_length=2000)


class Component(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,59}$")
    label: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=500)
    query: str = Field(min_length=1, max_length=20000)
    reference_query: str = Field(min_length=1, max_length=20000)
    order_sensitive: bool = False
    numeric_tolerance: float = Field(default=0, ge=0, le=0.01)


class Scenario(StrictModel):
    id: str = Field(pattern=r"^[a-zA-Z][a-zA-Z0-9_]{0,59}$")
    label: str = Field(min_length=1, max_length=100)
    visible: bool = False
    seed_sql: str = Field(max_length=200000)
    approved_outputs: dict[str, Output]


class IncidentDocument(StrictModel):
    title: str = Field(min_length=3, max_length=255)
    topic: str = Field(min_length=2, max_length=100)
    difficulty: Literal["easy", "medium", "hard"]
    report_style: Literal["investigation", "verdict"] = "investigation"
    complaint: str = Field(min_length=15, max_length=3000)
    business_rules: str = Field(min_length=15, max_length=5000)
    schema_sql: str = Field(min_length=10, max_length=100000)
    components: list[Component] = Field(min_length=1, max_length=4)
    culprit_component: str
    fault_template: str = Field(min_length=1, max_length=100)
    fault_cause: str = Field(min_length=10, max_length=3000)
    checkpoints: list[str] = Field(min_length=1, max_length=4)
    scenarios: list[Scenario] = Field(min_length=3, max_length=6)
    oracle_confirmed: bool = False
    alternative_repairs: list[str] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def relationships(self):
        if self.report_style == "verdict" and len(self.components) != 1:
            raise ValueError("Verdict incidents must contain one query to review")
        ids = [c.id for c in self.components]
        if len(ids) != len(set(ids)) or self.culprit_component not in ids:
            raise ValueError("Component IDs must be unique and include the culprit")
        if len({s.id for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("Scenario IDs must be unique")
        if sum(s.visible for s in self.scenarios) != 1:
            raise ValueError("Exactly one scenario must be visible")
        if any(set(s.approved_outputs) != set(ids) for s in self.scenarios):
            raise ValueError("Every scenario needs approved output for every component")
        if any(c.numeric_tolerance and any(len(s.approved_outputs[c.id].rows) > 200 for s in self.scenarios) for c in self.components):
            raise ValueError("Tolerance-based comparisons are limited to 200 rows per output")
        return self


class IncidentWrite(StrictModel):
    document: IncidentDocument
    source_id: int | None = None
    revision: int | None = None


class CompetitionConfig(StrictModel):
    missions: list[int] = Field(min_length=1, max_length=30)
    class_groups: list[str] = Field(default_factory=list, max_length=100)
    leaderboard: bool = True
    points: dict[str, int] = Field(default_factory=lambda: {"easy": 10, "medium": 20, "hard": 30})
    time_tiebreak: bool = True

    @model_validator(mode="after")
    def rules(self):
        if len(self.missions) != len(set(self.missions)):
            raise ValueError("An incident version cannot occur twice in a competition")
        if set(self.points) != {"easy", "medium", "hard"} or any(not isinstance(x, int) or x < 0 or x > 1000 for x in self.points.values()):
            raise ValueError("Points need bounded easy, medium and hard values")
        return self


class CompetitionWrite(StrictModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = Field(max_length=5000)
    topic: str = Field(min_length=2, max_length=100)
    config: CompetitionConfig
    opens_at: datetime | None = None
    closes_at: datetime | None = None

    @model_validator(mode="after")
    def dates(self):
        for value in (self.opens_at, self.closes_at):
            if value and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("Dates must include a time zone")
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValueError("Closing time must follow opening time")
        return self


class Report(StrictModel):
    verdict: Literal["", "correct", "incorrect"] = ""
    investigation_sql: str = Field(default="", max_length=20000)
    component_id: str = Field(default="", max_length=60)
    evidence: str = Field(default="", max_length=5000)
    diagnosis: str = Field(default="", max_length=5000)
    repair_sql: str = Field(default="", max_length=20000)
    explanation: str = Field(default="", max_length=5000)
    run_id: int | None = None


class DraftWrite(StrictModel):
    revision: int = Field(ge=0)
    report: Report


class RunRequest(StrictModel):
    query: str = Field(min_length=1, max_length=20000)
    component_id: str | None = Field(default=None, max_length=60)


class SubmitRequest(StrictModel):
    request_key: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    revision: int = Field(ge=0)


class ReviewRequest(StrictModel):
    diagnosis_score: int = Field(ge=0, le=3)
    explanation_score: int = Field(ge=0, le=3)
    rationale: str = Field(min_length=5, max_length=5000)


class ImportRequest(StrictModel):
    entries: list[dict[str, Any]] = Field(min_length=1, max_length=400)
    authorised: bool = False


class InspectionRequest(StrictModel):
    artifact_type: Literal["component", "table"]
    artifact_id: str = Field(min_length=1, max_length=100)


class SurveyRequest(StrictModel):
    usability: int = Field(ge=1, le=5)
    engagement: int = Field(ge=1, le=5)
    feedback: str = Field(default="", max_length=3000)


class AdaptRequest(StrictModel):
    template: Literal["left_to_inner", "remove_distinct", "invert_exists", "count_all"] = "left_to_inner"
    complaint: str = Field(min_length=15, max_length=3000)
    business_rules: str = Field(min_length=15, max_length=5000)


class WindowRequest(StrictModel):
    opens_at: datetime | None = None
    closes_at: datetime | None = None

    @model_validator(mode="after")
    def dates(self):
        for value in (self.opens_at, self.closes_at):
            if value and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError("Dates must include a time zone")
        if self.opens_at and self.closes_at and self.closes_at <= self.opens_at:
            raise ValueError("Closing time must follow opening time")
        return self
