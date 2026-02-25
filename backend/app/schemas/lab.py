from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# Lab schemas
class LabCreate(BaseModel):
    """Schema for creating a new lab"""
    title: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1)
    schema_sql: str = Field(..., min_length=1)
    sample_data_sql: str = Field(..., min_length=1)


class LabUpdate(BaseModel):
    """Schema for updating a lab"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1)
    schema_sql: Optional[str] = Field(None, min_length=1)
    sample_data_sql: Optional[str] = Field(None, min_length=1)


class LabListItem(BaseModel):
    """Schema for lab list item"""
    id: int
    title: str
    description: str
    is_published: bool
    is_running: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LabDetail(BaseModel):
    """Schema for detailed lab information"""
    id: int
    title: str
    description: str
    is_published: bool
    is_running: bool
    template_db_path: str
    schema_sql: str
    sample_data_sql: str
    created_by: int
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
