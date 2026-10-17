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


class ExampleOut(BaseModel):
    id: str
    title: str
    description: str
    schema_sql: str
    data_sql: str
    expressions: List[str]
