"""Project transport contracts. Formal engine contracts remain independently testable."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.normalization.schemas import (
    BusinessStatementResponse, IntegratedSubmissionInput, FunctionalDependencyInput,
)


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=255)
    difficulty: Literal["easy", "medium", "hard"]
    scenario: str = Field(min_length=1, max_length=20000)
    relation_name: str = Field(min_length=1, max_length=100)
    attributes: list[str] = Field(min_length=1, max_length=8)
    statements: list[BusinessStatementResponse] = Field(min_length=1, max_length=100)
    sample_rows: list[dict[str, str]] = Field(default_factory=list, max_length=100)
    target_normal_form: Literal["3NF", "BCNF"]
    approved_fds: list[FunctionalDependencyInput] = Field(min_length=1, max_length=64)
    semantic_judge_enabled: bool = False
    hide_correctness: bool = False
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def valid_domain(self):
        if len(set(self.attributes)) != len(self.attributes) or any(not a.strip() or len(a) > 100 for a in self.attributes):
            raise ValueError("Attributes must be unique, nonempty names of at most 100 characters.")
        ids = [s.id for s in self.statements]
        if len(ids) != len(set(ids)) or any(not s.id.strip() or not s.text.strip() or len(s.text) > 5000 for s in self.statements):
            raise ValueError("Business statements need unique nonempty IDs and text (up to 5000 characters).")
        domain = set(self.attributes)
        if any(set(row) != domain or any(len(v) > 1000 for v in row.values()) for row in self.sample_rows):
            raise ValueError("Each sample row must contain exactly the relation attributes; values are limited to 1000 characters.")
        for fd in self.approved_fds:
            if not set(fd.lhs + fd.rhs) <= domain:
                raise ValueError("Approved FDs contain unknown attributes.")
        return self


class SubmissionInput(IntegratedSubmissionInput):
    model_config = ConfigDict(extra="forbid")
    request_key: UUID
    exercise_version: str = Field(max_length=30)
    functional_dependencies: list[FunctionalDependencyInput] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def bounded_process(self):
        nodes = [self.process.root] + [c for s in self.process.steps for c in s.children]
        if len(nodes) > 99 or len(self.relations) > 50:
            raise ValueError("A decomposition may contain at most 99 nodes and 50 final relations.")
        if len({n.node_id for n in nodes}) != len(nodes):
            raise ValueError("Process node identifiers must be unique.")
        if any(len(n.name) > 100 or len(n.node_id) > 128 or len(n.attributes) > 8 for n in nodes):
            raise ValueError("Invalid relation size or identifier length.")
        if any(len(s.step_id) > 128 or len(s.parent_node_id) > 128 for s in self.process.steps):
            raise ValueError("Process identifiers are too long.")
        node_ids = {n.node_id for n in nodes}
        if any(p.node_id not in node_ids for p in self.canvas_positions):
            raise ValueError("Canvas positions reference unknown nodes.")
        return self


class ReviewInput(BaseModel):
    decision: Literal["accepted", "rejected"]
    reason: str = Field(min_length=1, max_length=2000)
    version: int = Field(ge=0)


class ReviewRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)
