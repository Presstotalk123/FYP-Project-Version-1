from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import sqlite3
import os

from app.database import get_db
from app.models.user import User
from app.models.lab import Lab
from app.models.lab_session import LabSession
from app.models.lab_attempt import LabAttempt
from app.models.lab_task import LabTask
from app.schemas.lab import (
    LabCreate, LabUpdate, LabListItem, LabDetail, LabResponse,
    SessionStart, SessionResponse, LabExecuteRequest, LabExecuteResponse,
    SchemaPreview, StopLabResponse, LabAttemptResponse, DatabaseStateResponse
)
from app.schemas.lab_task import (
    LabTaskCreate, LabTaskAssignAnswer, LabTaskUpdate, LabTaskResponse,
    LabTaskDetail, LabTaskValidateRequest, LabTaskValidateResponse
)
from app.dependencies import get_current_user, require_staff_role
from app.utils.lab_db_manager import (
    create_lab_template, copy_template_to_session, delete_session_database,
    delete_lab_template, get_lab_template_path, get_schema_info, LabDatabaseError
)
from app.utils.lab_cleanup import terminate_all_lab_sessions
from app.core.lab_query_executor import execute_lab_query
from app.core.answer_validator import generate_hash

router = APIRouter(prefix="/labs", tags=["labs"])


# ==============================================================================
# Lab CRUD Endpoints (Staff Only)
# ==============================================================================

@router.post("", response_model=LabResponse, status_code=status.HTTP_201_CREATED)
def create_lab(
    lab_data: LabCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Create a new lab (Staff only).
    Creates a template database with the provided schema and data.
    """
    # Create lab record first (without template_db_path)
    lab = Lab(
        title=lab_data.title,
        description=lab_data.description,
        schema_sql=lab_data.schema_sql,
        sample_data_sql=lab_data.sample_data_sql,
        template_db_path="",  # Will be set after creation
        created_by=current_user.id,
        is_published=0,
        is_running=0,
        is_deleted=0
    )
    db.add(lab)
    db.flush()  # Get the lab ID

    # Create template database
    try:
        template_path = create_lab_template(
            lab.id,
            lab_data.schema_sql,
            lab_data.sample_data_sql
        )
        lab.template_db_path = f"lab_{lab.id}_template.db"
        db.commit()
    except LabDatabaseError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create lab database: {str(e)}"
        )

    db.refresh(lab)
    return LabResponse(
        id=lab.id,
        title=lab.title,
        description=lab.description,
        is_published=bool(lab.is_published),
        is_running=bool(lab.is_running),
        created_at=lab.created_at,
        updated_at=lab.updated_at
    )


@router.get("", response_model=List[LabListItem])
def list_labs(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List labs.
    Students: only published labs (is_published=1)
    Staff: all non-deleted labs
    """
    query = db.query(Lab).filter(Lab.is_deleted == 0)

    # Filter by role
    if current_user.role.value == "student":
        query = query.filter(Lab.is_published == 1)

    labs = query.order_by(Lab.created_at.desc()).offset(skip).limit(limit).all()

    return [
        LabListItem(
            id=lab.id,
            title=lab.title,
            description=lab.description,
            is_published=bool(lab.is_published),
            is_running=bool(lab.is_running),
            created_at=lab.created_at,
            updated_at=lab.updated_at
        )
        for lab in labs
    ]


@router.get("/{lab_id}", response_model=LabDetail)
def get_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get lab details.
    Students: only if published
    Staff: any lab
    """
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Check permissions for students
    if current_user.role.value == "student" and not lab.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    return LabDetail(
        id=lab.id,
        title=lab.title,
        description=lab.description,
        is_published=bool(lab.is_published),
        is_running=bool(lab.is_running),
        template_db_path=lab.template_db_path,
        schema_sql=lab.schema_sql,
        sample_data_sql=lab.sample_data_sql,
        created_by=lab.created_by,
        created_at=lab.created_at,
        updated_at=lab.updated_at
    )


@router.put("/{lab_id}", response_model=LabResponse)
def update_lab(
    lab_id: int,
    lab_data: LabUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Update lab (Staff only).
    Can only edit if lab is not running.
    If SQL changed, regenerates template database.
    """
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Cannot edit while running
    if lab.is_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit lab while it is running. Stop the lab first."
        )

    # Check if SQL changed
    sql_changed = False
    if lab_data.schema_sql and lab_data.schema_sql != lab.schema_sql:
        sql_changed = True
    if lab_data.sample_data_sql and lab_data.sample_data_sql != lab.sample_data_sql:
        sql_changed = True

    # Update fields
    if lab_data.title:
        lab.title = lab_data.title
    if lab_data.description:
        lab.description = lab_data.description
    if lab_data.schema_sql:
        lab.schema_sql = lab_data.schema_sql
    if lab_data.sample_data_sql:
        lab.sample_data_sql = lab_data.sample_data_sql

    # Regenerate template if SQL changed
    if sql_changed:
        try:
            template_path = create_lab_template(
                lab.id,
                lab.schema_sql,
                lab.sample_data_sql
            )
        except LabDatabaseError as e:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to regenerate lab database: {str(e)}"
            )

    lab.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lab)

    return LabResponse(
        id=lab.id,
        title=lab.title,
        description=lab.description,
        is_published=bool(lab.is_published),
        is_running=bool(lab.is_running),
        created_at=lab.created_at,
        updated_at=lab.updated_at
    )


@router.delete("/{lab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Delete lab (Staff only).
    Soft delete: sets is_deleted=1.
    If running, stops first and terminates all sessions.
    Deletes template database.
    """
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # If running, stop it first
    if lab.is_running:
        terminate_all_lab_sessions(lab_id, db)
        lab.is_running = 0

    # Soft delete
    lab.is_deleted = 1
    lab.updated_at = datetime.utcnow()
    db.commit()

    # Delete template database
    delete_lab_template(lab_id)

    return None


# ==============================================================================
# Lab State Management Endpoints (Staff Only)
# ==============================================================================

@router.post("/{lab_id}/publish", response_model=LabResponse)
def publish_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Publish a lab (Staff only).
    Sets is_published=1.
    """
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    lab.is_published = 1
    lab.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lab)

    return LabResponse(
        id=lab.id,
        title=lab.title,
        description=lab.description,
        is_published=bool(lab.is_published),
        is_running=bool(lab.is_running),
        created_at=lab.created_at,
        updated_at=lab.updated_at
    )


@router.post("/{lab_id}/unpublish", response_model=LabResponse)
def unpublish_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Unpublish a lab (Staff only).
    Sets is_published=0.
    If running, stops it first (terminates all sessions).
    """
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # If running, stop it first
    if lab.is_running:
        terminate_all_lab_sessions(lab_id, db)
        lab.is_running = 0

    lab.is_published = 0
    lab.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lab)

    return LabResponse(
        id=lab.id,
        title=lab.title,
        description=lab.description,
        is_published=bool(lab.is_published),
        is_running=bool(lab.is_running),
        created_at=lab.created_at,
        updated_at=lab.updated_at
    )


@router.post("/{lab_id}/start", response_model=LabResponse)
def start_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Start a lab (Staff only).
    Sets is_running=1.
    Lab must be published first.
    """
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Must be published to start
    if not lab.is_published:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lab must be published before starting"
        )

    lab.is_running = 1
    lab.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lab)

    return LabResponse(
        id=lab.id,
        title=lab.title,
        description=lab.description,
        is_published=bool(lab.is_published),
        is_running=bool(lab.is_running),
        created_at=lab.created_at,
        updated_at=lab.updated_at
    )


@router.post("/{lab_id}/stop", response_model=StopLabResponse)
def stop_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Stop a lab (Staff only).
    Sets is_running=0.
    Terminates all active sessions and deletes student database files.
    """
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Terminate all active sessions
    terminated_count = terminate_all_lab_sessions(lab_id, db)

    lab.is_running = 0
    lab.updated_at = datetime.utcnow()
    db.commit()

    return StopLabResponse(
        message=f"Lab stopped successfully",
        sessions_terminated=terminated_count
    )


# ==============================================================================
# Student Session Endpoints
# ==============================================================================

@router.post("/{lab_id}/session/start", response_model=SessionStart)
def start_session(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Start a lab session (Student/Staff).
    Students: Requires lab to be published AND running.
    Staff: Can access any lab for testing purposes.
    Idempotent: returns existing session if active.
    Creates a database copy for the user.
    """
    # Get lab
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Check if lab is published and running (students only - staff can test any lab)
    if current_user.role.value == "student":
        if not lab.is_published or not lab.is_running:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lab is not available for sessions"
            )

    # Check for existing active session (idempotent)
    existing_session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id,
        LabSession.user_id == current_user.id,
        LabSession.is_active == 1
    ).first()

    if existing_session:
        return SessionStart(
            session_id=existing_session.id,
            lab_id=existing_session.lab_id,
            started_at=existing_session.started_at
        )

    # Copy template database to create session database
    try:
        session_db_path = copy_template_to_session(lab_id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create session database: {str(e)}"
        )

    # Create session record
    session = LabSession(
        lab_id=lab_id,
        user_id=current_user.id,
        db_file_path=session_db_path,
        is_active=1
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return SessionStart(
        session_id=session.id,
        lab_id=session.lab_id,
        started_at=session.started_at
    )


@router.get("/{lab_id}/session", response_model=SessionResponse)
def get_session(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get active session for current user (Student/Staff).
    Returns 404 if no active session exists.
    """
    session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id,
        LabSession.user_id == current_user.id,
        LabSession.is_active == 1
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active session found"
        )

    return SessionResponse(
        id=session.id,
        lab_id=session.lab_id,
        user_id=session.user_id,
        is_active=bool(session.is_active),
        started_at=session.started_at,
        ended_at=session.ended_at
    )


@router.post("/session/{session_id}/execute", response_model=LabExecuteResponse)
def execute_query(
    session_id: int,
    execute_request: LabExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute a SQL query in a lab session (Student/Staff).
    Verifies session is active and belongs to current user.
    Allows all SQL statements (SELECT, INSERT, UPDATE, DELETE, CREATE, etc.)
    15-second timeout.
    """
    # Get session
    session = db.query(LabSession).filter(
        LabSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    # Verify session belongs to current user
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session"
        )

    # Verify session is active
    if not session.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active"
        )

    # Verify lab is still running (students only - staff can execute queries anytime for testing)
    lab = db.query(Lab).filter(Lab.id == session.lab_id).first()
    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    if current_user.role.value == "student" and not lab.is_running:
        # Auto-terminate session if lab stopped (students only)
        from app.utils.lab_cleanup import terminate_session
        terminate_session(session, db)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Lab is no longer running"
        )

    # Execute query on student's database
    result = execute_lab_query(session.db_file_path, execute_request.query, timeout=15)

    # Save attempt to history
    attempt = LabAttempt(
        session_id=session.id,
        lab_id=session.lab_id,
        user_id=current_user.id,
        query=execute_request.query,
        success=1 if result["success"] else 0,
        execution_time_ms=result["execution_time_ms"],
        row_count=result["row_count"],
        error_message=result["error_message"]
    )
    db.add(attempt)
    db.commit()

    return LabExecuteResponse(
        success=result["success"],
        columns=result["columns"],
        results=result["results"],
        execution_time_ms=result["execution_time_ms"],
        row_count=result["row_count"],
        error_message=result["error_message"]
    )


@router.get("/session/{session_id}/attempts", response_model=List[LabAttemptResponse])
def get_session_attempts(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get attempt history for a lab session (Student/Staff).
    Returns list of previous queries and their results.
    """
    # Get session
    session = db.query(LabSession).filter(
        LabSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )

    # Verify session belongs to current user
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this session"
        )

    # Get attempts for this session
    attempts = db.query(LabAttempt).filter(
        LabAttempt.session_id == session_id
    ).order_by(LabAttempt.submitted_at.desc()).all()

    return [
        LabAttemptResponse(
            id=attempt.id,
            query=attempt.query,
            success=bool(attempt.success),
            execution_time_ms=attempt.execution_time_ms,
            row_count=attempt.row_count,
            error_message=attempt.error_message,
            submitted_at=attempt.submitted_at
        )
        for attempt in attempts
    ]


@router.get("/session/{session_id}/database", response_model=DatabaseStateResponse)
def get_session_database_state(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current database state for active session (Student).
    Returns tables, schema, row counts, and sample data from the student's current database.
    """
    # Get session
    session = db.query(LabSession).filter(
        LabSession.id == session_id,
        LabSession.user_id == current_user.id,
        LabSession.is_active == 1
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active session not found"
        )

    # Verify database file exists
    if not os.path.exists(session.db_file_path):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session database file not found"
        )

    # Get schema info
    from app.utils.lab_db_manager import get_schema_info
    schema_data = get_schema_info(session.db_file_path)

    # For each table, get row count and sample data
    tables_with_data = []
    conn = sqlite3.connect(f"file:{session.db_file_path}?mode=ro", uri=True)

    try:
        for table_info in schema_data["tables"]:
            table_name = table_info["name"]
            cursor = conn.cursor()

            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]

            # Get sample data (first 20 rows)
            cursor.execute(f"SELECT * FROM {table_name} LIMIT 20")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            tables_with_data.append({
                "name": table_name,
                "columns": table_info["columns"],
                "create_sql": table_info["create_sql"],
                "row_count": row_count,
                "sample_data": {
                    "columns": columns,
                    "rows": [dict(zip(columns, row)) for row in rows]
                }
            })

            cursor.close()

    finally:
        conn.close()

    return {"tables": tables_with_data}


@router.post("/{lab_id}/session/reset")
def reset_session(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reset lab session database to original template (Student/Staff).
    Deletes current database and creates fresh copy from template.
    """
    # Get active session
    session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id,
        LabSession.user_id == current_user.id,
        LabSession.is_active == 1
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active session found"
        )

    # Delete current database file
    delete_session_database(session.db_file_path)

    # Copy template database to create fresh session
    try:
        session_db_path = copy_template_to_session(lab_id, current_user.id)
        session.db_file_path = session_db_path
        db.commit()
    except LabDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset session database: {str(e)}"
        )

    return {"message": "Session database reset successfully"}


@router.post("/{lab_id}/session/exit")
def exit_session(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Exit a lab session (Student/Staff).
    Terminates active session and deletes database file.
    """
    # Get active session
    session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id,
        LabSession.user_id == current_user.id,
        LabSession.is_active == 1
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active session found"
        )

    # Terminate session
    from app.utils.lab_cleanup import terminate_session
    if not terminate_session(session, db):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to terminate session"
        )

    return {"message": "Session ended successfully"}


# ==============================================================================
# Preview Endpoint
# ==============================================================================

@router.get("/{lab_id}/preview/schema", response_model=SchemaPreview)
def preview_schema(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get schema information for preview (Student/Staff).
    Students: only if lab is published
    Staff: always
    Read-only connection to template database.
    """
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Check permissions for students
    if current_user.role.value == "student" and not lab.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Get schema info from template database
    template_path = get_lab_template_path(lab_id)
    try:
        schema_info = get_schema_info(template_path)
        return SchemaPreview(tables=schema_info["tables"])
    except LabDatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read schema: {str(e)}"
        )


# ==============================================================================
# Lab Task Endpoints
# ==============================================================================

@router.post("/{lab_id}/tasks", response_model=LabTaskResponse, status_code=status.HTTP_201_CREATED)
def create_lab_task(
    lab_id: int,
    task_data: LabTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Create a new lab task without answer (Staff only).
    Answer can be assigned later via the assign endpoint.
    """
    # Verify lab exists
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Create task without answer
    task = LabTask(
        lab_id=lab_id,
        title=task_data.title,
        description=task_data.description,
        order_index=task_data.order_index,
        created_by=current_user.id,
        correct_answer_hash=None,  # Will be assigned later
        correct_query=None
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    # Return response with has_answer computed field
    return LabTaskResponse(
        id=task.id,
        lab_id=task.lab_id,
        title=task.title,
        description=task.description,
        order_index=task.order_index,
        has_answer=task.correct_answer_hash is not None,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.get("/{lab_id}/tasks", response_model=List[LabTaskResponse])
def list_lab_tasks(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all tasks for a lab (Student/Staff).
    Students: Only if lab is published
    Staff: Always
    """
    # Verify lab exists and check permissions
    lab = db.query(Lab).filter(
        Lab.id == lab_id,
        Lab.is_deleted == 0
    ).first()

    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Check permissions for students
    if current_user.role.value == "student" and not lab.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Get tasks
    tasks = db.query(LabTask).filter(
        LabTask.lab_id == lab_id,
        LabTask.is_deleted == 0
    ).order_by(LabTask.order_index, LabTask.created_at).all()

    # Return with has_answer computed field
    return [
        LabTaskResponse(
            id=task.id,
            lab_id=task.lab_id,
            title=task.title,
            description=task.description,
            order_index=task.order_index,
            has_answer=task.correct_answer_hash is not None,
            created_by=task.created_by,
            created_at=task.created_at,
            updated_at=task.updated_at
        )
        for task in tasks
    ]


@router.post("/{lab_id}/tasks/{task_id}/assign", response_model=LabTaskResponse)
def assign_task_answer(
    lab_id: int,
    task_id: int,
    assign_data: LabTaskAssignAnswer,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Assign a query result as the correct answer for a task (Staff only).
    Executes the query on the template database and generates a hash.
    """
    # Get task
    task = db.query(LabTask).filter(
        LabTask.id == task_id,
        LabTask.lab_id == lab_id,
        LabTask.is_deleted == 0
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    # Execute query on template database to generate hash
    try:
        template_path = get_lab_template_path(lab_id)
        result = execute_lab_query(template_path, assign_data.query, timeout=15)

        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Query validation failed: {result['error_message']}"
            )

        # Convert dict results to tuple format for hash generation
        results_tuples = [
            tuple(row[col] for col in result["columns"])
            for row in result["results"]
        ]

        # Generate hash from results
        correct_hash = generate_hash(results_tuples, result["columns"])

        # Update task with answer
        task.correct_query = assign_data.query
        task.correct_answer_hash = correct_hash
        task.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(task)

    except LabDatabaseError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to execute query: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to assign answer: {str(e)}"
        )

    return LabTaskResponse(
        id=task.id,
        lab_id=task.lab_id,
        title=task.title,
        description=task.description,
        order_index=task.order_index,
        has_answer=task.correct_answer_hash is not None,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.get("/{lab_id}/tasks/{task_id}", response_model=LabTaskDetail)
def get_lab_task(
    lab_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Get detailed task information including correct query (Staff only).
    """
    task = db.query(LabTask).filter(
        LabTask.id == task_id,
        LabTask.lab_id == lab_id,
        LabTask.is_deleted == 0
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    return LabTaskDetail(
        id=task.id,
        lab_id=task.lab_id,
        title=task.title,
        description=task.description,
        order_index=task.order_index,
        has_answer=task.correct_answer_hash is not None,
        correct_query=task.correct_query,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.put("/{lab_id}/tasks/{task_id}", response_model=LabTaskResponse)
def update_lab_task(
    lab_id: int,
    task_id: int,
    task_data: LabTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Update a lab task metadata (Staff only).
    Does not update the answer - use assign endpoint for that.
    """
    task = db.query(LabTask).filter(
        LabTask.id == task_id,
        LabTask.lab_id == lab_id,
        LabTask.is_deleted == 0
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    # Update fields
    if task_data.title is not None:
        task.title = task_data.title
    if task_data.description is not None:
        task.description = task_data.description
    if task_data.order_index is not None:
        task.order_index = task_data.order_index

    task.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(task)

    return LabTaskResponse(
        id=task.id,
        lab_id=task.lab_id,
        title=task.title,
        description=task.description,
        order_index=task.order_index,
        has_answer=task.correct_answer_hash is not None,
        created_by=task.created_by,
        created_at=task.created_at,
        updated_at=task.updated_at
    )


@router.delete("/{lab_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_lab_task(
    lab_id: int,
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Soft delete a lab task (Staff only).
    """
    task = db.query(LabTask).filter(
        LabTask.id == task_id,
        LabTask.lab_id == lab_id,
        LabTask.is_deleted == 0
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    task.is_deleted = 1
    task.updated_at = datetime.utcnow()
    db.commit()

    return None


@router.post("/tasks/validate", response_model=LabTaskValidateResponse)
def validate_task_answer(
    validate_request: LabTaskValidateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Validate student's answer against task's correct hash (Student/Staff).
    Verifies session belongs to user and is active.
    """
    # Get task
    task = db.query(LabTask).filter(
        LabTask.id == validate_request.task_id,
        LabTask.is_deleted == 0
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    # Check if task has an answer assigned
    if not task.correct_answer_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task does not have an answer assigned yet"
        )

    # Get session and verify ownership
    session = db.query(LabSession).filter(
        LabSession.id == validate_request.session_id,
        LabSession.user_id == current_user.id,
        LabSession.is_active == 1
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active session not found"
        )

    # Execute user's query on their session database
    result = execute_lab_query(session.db_file_path, validate_request.user_query, timeout=15)

    if not result["success"]:
        return LabTaskValidateResponse(
            is_correct=False,
            message=f"Query failed: {result['error_message']}"
        )

    # Generate hash from user results
    results_tuples = [
        tuple(row[col] for col in result["columns"])
        for row in result["results"]
    ]
    user_hash = generate_hash(results_tuples, result["columns"])

    # Compare hashes
    is_correct = user_hash == task.correct_answer_hash

    return LabTaskValidateResponse(
        is_correct=is_correct,
        message="Correct! Your query produces the expected result." if is_correct
                else "Incorrect. Your query result doesn't match the expected answer."
    )
