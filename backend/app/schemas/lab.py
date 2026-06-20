from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# Lab schemas
class LabUpdate(BaseModel):
    """Schema for updating a lab"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)


class LabListItem(BaseModel):
    """Schema for lab list item"""
    id: int
    title: str
    description: str
    is_published: bool
    is_running: bool
    lab_type: str = "sql"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LabResponse(BaseModel):
    """Schema for lab response"""
    id: int
    title: str
    description: str
    is_published: bool
    is_running: bool
    lab_type: str = "sql"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Session schemas
class SessionStart(BaseModel):
    """Schema for starting a session response"""
    session_id: int
    lab_id: int
    started_at: datetime


class SessionResponse(BaseModel):
    """Schema for session information"""
    id: int
    lab_id: int
    user_id: int
    is_active: bool
    started_at: datetime
    ended_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Query execution schemas
class LabExecuteRequest(BaseModel):
    """Schema for lab query execution request"""
    query: str = Field(..., min_length=1)
    is_review_mode: Optional[bool] = False


class LabExecuteResponse(BaseModel):
    """Schema for lab query execution response"""
    success: bool
    columns: List[str]
    results: List[dict]
    execution_time_ms: float
    row_count: int
    error_message: Optional[str] = None


# Preview schemas
class ColumnInfo(BaseModel):
    """Schema for column information"""
    name: str
    type: str
    notnull: bool
    default_value: Optional[str] = None
    pk: bool


class TableInfo(BaseModel):
    """Schema for table information"""
    name: str
    columns: List[ColumnInfo]
    create_sql: str


class SchemaPreview(BaseModel):
    """Schema for database schema preview"""
    tables: List[TableInfo]


# State management schemas
class StopLabResponse(BaseModel):
    """Schema for stop lab response"""
    message: str
    sessions_terminated: int


# Attempt schemas
class LabAttemptResponse(BaseModel):
    """Schema for lab attempt history"""
    id: int
    query: str
    success: bool
    execution_time_ms: float
    row_count: int
    error_message: Optional[str] = None
    submitted_at: datetime

    class Config:
        from_attributes = True


class LabQueryHistoryResponse(BaseModel):
    """Schema for comprehensive lab query history across sessions"""
    id: int
    lab_id: int
    lab_title: str
    session_id: int
    session_started_at: datetime
    session_ended_at: Optional[datetime] = None
    query: str
    success: bool
    execution_time_ms: float
    row_count: int
    error_message: Optional[str] = None
    submitted_at: datetime
    student_email: Optional[str] = None

    class Config:
        from_attributes = True


# Database state schemas
class TableSampleData(BaseModel):
    """Schema for table sample data"""
    columns: List[str]
    rows: List[Dict[str, Any]]


class TableStateResponse(BaseModel):
    """Schema for table state with data"""
    name: str
    columns: List[ColumnInfo]
    create_sql: str
    row_count: int
    sample_data: TableSampleData


class DatabaseStateResponse(BaseModel):
    """Schema for complete database state"""
    tables: List[TableStateResponse]


# Student attempts schemas
class StudentAttemptSummary(BaseModel):
    """Summary of a student's task attempts for a lab"""
    user_id: int
    email: str
    correct_count: int
    not_solved_count: int
    total_tasks: int
    last_submission_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LabStudentAttemptsResponse(BaseModel):
    """Response containing all student attempt summaries for a lab"""
    lab_id: int
    lab_title: str
    total_tasks: int
    students: List[StudentAttemptSummary]


# ---------------------------------------------------------------------------
# Unified lab schemas (Tasks 2+)
# ---------------------------------------------------------------------------
from typing import Literal

LabItemKind = Literal["sql", "erd", "sqllab"]


class UnifiedLabCreate(BaseModel):
    """Create a unified lab (pool items only; no manual shared-DB section)."""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    join_password: str = Field(..., min_length=4, max_length=64)


class LabItemCreate(BaseModel):
    kind: LabItemKind
    ref_id: Optional[int] = None            # required for sql/erd; null for sqllab


class LabItemResponse(BaseModel):
    id: int
    kind: LabItemKind
    ref_id: Optional[int] = None
    order_index: int
    title: str                              # resolved from the referenced question / section
    difficulty: Optional[str] = None

    class Config:
        from_attributes = True


class LabReorderRequest(BaseModel):
    item_ids: List[int]                     # full ordered list of lab_item ids


class UnifiedLabDetail(BaseModel):
    id: int
    title: str
    description: str
    is_published: bool
    is_running: bool
    items: List[LabItemResponse]

    class Config:
        from_attributes = True


class JoinLabRequest(BaseModel):
    join_password: Optional[str] = None     # staff may omit


class SqlItemSubmit(BaseModel):
    """Submit for a `sql` lab item or a `sqllab` question task."""
    query: str = Field(..., min_length=1)
    lab_task_id: Optional[int] = None       # set only for a sqllab-question task


class SqlLabRunRequest(BaseModel):
    """Run arbitrary SQL against the per-(session,item) writable DB."""
    query: str = Field(..., min_length=1)


class SqlLabRunResult(BaseModel):
    success: bool
    columns: List[str] = []
    results: List[dict] = []
    row_count: int = 0
    error_message: Optional[str] = None

    @classmethod
    def from_executor(cls, r: dict) -> "SqlLabRunResult":
        return cls(success=r["success"], columns=r["columns"], results=r["results"],
                   row_count=r["row_count"], error_message=r["error_message"])


class ItemGradeResponse(BaseModel):
    is_passed: bool
    score_earned: Optional[float] = None
    score_total: Optional[float] = None
    message: str


class DatabaseColumn(BaseModel):
    name: str
    type: str


class DatabaseTableState(BaseModel):
    name: str
    columns: List[DatabaseColumn]
    row_count: int
    sample_rows: List[dict] = []


class DatabaseState(BaseModel):
    """Live snapshot of a student's writable SQL-lab DB (for the 'Database' browser)."""
    tables: List[DatabaseTableState] = []


class LabItemProgress(BaseModel):
    lab_item_id: int
    kind: LabItemKind
    lab_task_id: Optional[int] = None
    is_passed: bool
    score_percent: Optional[float] = None


class LabProgressResponse(BaseModel):
    lab_id: int
    done: int
    total: int
    items: List[LabItemProgress]


class SubmissionOverrideRequest(BaseModel):
    score_earned: float
    score_total: float = Field(..., gt=0)
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Task 13: Staff monitoring schemas
# ---------------------------------------------------------------------------

class LabStudentSummary(BaseModel):
    user_id: int
    email: str
    passed_items: int
    total_items: int
    last_submitted_at: Optional[datetime] = None


class LabStudentsResponse(BaseModel):
    lab_id: int
    total_items: int
    students: List[LabStudentSummary]


class LabSubmissionView(BaseModel):
    id: int
    lab_item_id: int
    kind: str
    item_title: str
    is_passed: bool
    score_earned: Optional[float] = None
    score_total: Optional[float] = None
    override_score_earned: Optional[float] = None
    override_score_total: Optional[float] = None
    submitted_at: datetime
