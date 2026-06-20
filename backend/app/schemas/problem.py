from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ProblemType = Literal["sql", "erd", "sqllab", "graph"]
ProblemDifficulty = Literal["easy", "medium", "hard"]
CreatorRole = Literal["student", "staff"]


class ProblemListItem(BaseModel):
    type: ProblemType
    id: int
    title: str
    difficulty: ProblemDifficulty
    created_by: int
    created_by_role: CreatorRole
    created_at: datetime


class ProblemCounts(BaseModel):
    all: int
    sql: int
    erd: int
    sqllab: int
    graph: int


class ProblemListResponse(BaseModel):
    items: list[ProblemListItem]
    counts: ProblemCounts
