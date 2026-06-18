from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from datetime import datetime
import json as _json
import logging

from app.database import get_db
from app.models.user import User
from app.models.lab import Lab
from app.models.lab_session import LabSession
from app.models.lab_attempt import LabAttempt
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.lab_item import LabItem
from app.models.lab_submission import LabSubmission
from app.core.security import hash_password, verify_password
from app.services.lab_items.registry import get_handler, HANDLERS
from collections import defaultdict
from app.schemas.lab import (
    LabUpdate, LabListItem, LabResponse,
    SessionStart, SessionResponse, LabExecuteRequest, LabExecuteResponse,
    SchemaPreview, StopLabResponse, LabAttemptResponse, DatabaseStateResponse,
    LabQueryHistoryResponse, StudentAttemptSummary, LabStudentAttemptsResponse,
    UnifiedLabCreate, LabItemCreate, LabItemResponse, LabReorderRequest,
    UnifiedLabDetail, JoinLabRequest, SqlItemSubmit, ItemGradeResponse,
    LabItemProgress, LabProgressResponse, SubmissionOverrideRequest,
    LabStudentSummary, LabStudentsResponse, LabSubmissionView,
)
from app.schemas.lab_task import (
    LabTaskCreate, LabTaskAssignAnswer, LabTaskUpdate, LabTaskResponse,
    LabTaskDetail, LabTaskValidateRequest, LabTaskValidateResponse,
    LabTaskSubmitRequest, LabTaskSubmitResponse, LabTaskProgress, LabTaskProgressResponse
)
from app.dependencies import get_current_user, require_staff_role
from app.utils.lab_db_manager import (
    delete_lab_template, get_lab_template_path, get_schema_info, LabDatabaseError
)
from app.utils.lab_cleanup import terminate_all_lab_sessions
from app.core.lab_query_executor import execute_lab_query
from app.core.answer_validator import generate_hash
from app.models.sql_lab_question import SqlLabTask
from app.utils.sqllab_db_manager import ensure_sqllab_session, reset_sqllab_session, introspect_db
from app.schemas.lab import SqlLabTaskView, SqlLabRunRequest, SqlLabRunResult, DatabaseState

router = APIRouter(prefix="/labs", tags=["labs"])
logger = logging.getLogger(__name__)


# ==============================================================================
# Lab CRUD Endpoints (Staff Only)
# ==============================================================================

@router.post("", status_code=status.HTTP_201_CREATED)
def create_lab(
    lab_data: UnifiedLabCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    lab = Lab(
        title=lab_data.title,
        description=lab_data.description,
        join_password_hash=hash_password(lab_data.join_password),
        join_password_plain=lab_data.join_password,
        created_by=current_user.id,
        is_published=0, is_running=0, is_deleted=0,
    )
    db.add(lab); db.commit(); db.refresh(lab)
    return {
        "id": lab.id, "title": lab.title, "description": lab.description,
        "is_published": bool(lab.is_published), "is_running": bool(lab.is_running),
        "created_at": lab.created_at, "updated_at": lab.updated_at,
        "join_password": lab.join_password_plain,
    }


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


def _item_view(db, item):
    try:
        v = get_handler(item.kind).to_view(db, item.ref_id)
        return LabItemResponse(id=item.id, kind=item.kind, ref_id=item.ref_id,
                               order_index=item.order_index, title=v.title, difficulty=v.difficulty)
    except ValueError:
        return LabItemResponse(id=item.id, kind=item.kind, ref_id=item.ref_id,
                               order_index=item.order_index, title="(unavailable)", difficulty=None)


@router.get("/{lab_id}", response_model=UnifiedLabDetail)
def get_lab_detail(lab_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    lab = db.query(Lab).filter(Lab.id == lab_id, Lab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    if current_user.role.value == "student" and not lab.is_published:
        raise HTTPException(status_code=404, detail="Lab not found")
    items = (db.query(LabItem).filter(LabItem.lab_id == lab_id, LabItem.is_deleted == 0)
             .order_by(LabItem.order_index).all())
    return UnifiedLabDetail(
        id=lab.id, title=lab.title, description=lab.description,
        is_published=bool(lab.is_published), is_running=bool(lab.is_running),
        items=[_item_view(db, it) for it in items],
    )


def _staff_lab_or_404(db, lab_id, current_user):
    lab = db.query(Lab).filter(Lab.id == lab_id, Lab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    return lab


@router.post("/{lab_id}/items", status_code=status.HTTP_201_CREATED, response_model=LabItemResponse)
def add_lab_item(lab_id: int, body: LabItemCreate, db: Session = Depends(get_db),
                 current_user: User = Depends(require_staff_role)):
    lab = _staff_lab_or_404(db, lab_id, current_user)
    if lab.is_running:
        raise HTTPException(status_code=400, detail="Cannot edit a running lab")
    if body.kind in ("sql", "erd", "sqllab"):
        if body.ref_id is None:
            raise HTTPException(status_code=400, detail="ref_id is required")
        try:
            get_handler(body.kind).resolve(db, body.ref_id)  # 404 if the pool question is gone
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail="Unknown item kind")

    next_order = db.query(LabItem).filter(LabItem.lab_id == lab_id, LabItem.is_deleted == 0).count()
    item = LabItem(lab_id=lab_id, kind=body.kind, ref_id=body.ref_id, order_index=next_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _item_view(db, item)


@router.delete("/{lab_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_lab_item(lab_id: int, item_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_staff_role)):
    lab = _staff_lab_or_404(db, lab_id, current_user)
    if lab.is_running:
        raise HTTPException(status_code=400, detail="Cannot edit a running lab")
    item = db.query(LabItem).filter(LabItem.id == item_id, LabItem.lab_id == lab_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    item.is_deleted = 1
    db.commit()
    return None


@router.put("/{lab_id}/items/order", status_code=status.HTTP_200_OK)
def reorder_lab_items(lab_id: int, body: LabReorderRequest, db: Session = Depends(get_db),
                      current_user: User = Depends(require_staff_role)):
    lab = _staff_lab_or_404(db, lab_id, current_user)
    if lab.is_running:
        raise HTTPException(status_code=400, detail="Cannot edit a running lab")
    items = {i.id: i for i in db.query(LabItem).filter(LabItem.lab_id == lab_id, LabItem.is_deleted == 0).all()}
    if set(body.item_ids) != set(items.keys()):
        raise HTTPException(status_code=400, detail="item_ids must list exactly the lab's items")
    for order, item_id in enumerate(body.item_ids):
        items[item_id].order_index = order
    db.commit()
    return {"ok": True}


@router.put("/{lab_id}", response_model=LabResponse)
def update_lab(
    lab_id: int,
    lab_data: LabUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Update lab metadata (Staff only).
    Can only edit if lab is not running. The manual shared-DB section was
    removed, so only title/description are editable here.
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

    # Update editable fields (schema_sql/sample_data_sql no longer apply)
    if lab_data.title:
        lab.title = lab_data.title
    if lab_data.description:
        lab.description = lab_data.description

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

    has_items = db.query(LabItem).filter(LabItem.lab_id == lab_id, LabItem.is_deleted == 0).count()
    if not has_items:
        raise HTTPException(status_code=400, detail="Cannot publish an empty lab")

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

@router.post("/{lab_id}/session/start", response_model=SessionResponse)
def start_session(lab_id: int, body: JoinLabRequest, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    lab = db.query(Lab).filter(Lab.id == lab_id, Lab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    is_staff = current_user.role.value == "staff"
    if not is_staff and not (lab.is_published and lab.is_running):
        raise HTTPException(status_code=400, detail="Lab is not open")

    # Already joined? Resume the existing session WITHOUT re-checking the password. The
    # workspace calls this endpoint with no password on load, so re-checking here would
    # reject a student who already joined — and the frontend's global 401 handler would
    # then log them out.
    existing = db.query(LabSession).filter(
        LabSession.lab_id == lab_id, LabSession.user_id == current_user.id, LabSession.is_active == 1
    ).first()
    if existing:
        return existing

    # New join: students must supply the correct join password. Use 403 (a forbidden
    # action), NOT 401 — a 401 means "not authenticated" and trips the frontend's global
    # logout-on-401 interceptor, kicking the student to the login screen.
    if not is_staff and not verify_password(body.join_password or "", lab.join_password_hash):
        raise HTTPException(status_code=403, detail="Incorrect join password")

    session = LabSession(lab_id=lab_id, user_id=current_user.id, is_active=1)
    db.add(session); db.commit(); db.refresh(session)
    return session


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


# ==============================================================================
# Item Submit / Progress / Override Endpoints
# ==============================================================================

@router.post("/{lab_id}/items/{item_id}/submit", response_model=ItemGradeResponse)
def submit_item(lab_id: int, item_id: int, body: SqlItemSubmit, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    item = db.query(LabItem).filter(LabItem.id == item_id, LabItem.lab_id == lab_id,
                                    LabItem.is_deleted == 0).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.kind == "erd":
        raise HTTPException(status_code=400, detail="Use the streaming /submission endpoint for ERD items")
    session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id, LabSession.user_id == current_user.id, LabSession.is_active == 1
    ).first()
    if not session:
        raise HTTPException(status_code=400, detail="No active session")

    result = get_handler(item.kind).grade(
        db, item.ref_id, {"query": body.query, "lab_task_id": body.lab_task_id, "lab_item_id": item.id}, session
    )
    sub = LabSubmission(
        lab_id=lab_id, lab_item_id=item.id, lab_task_id=body.lab_task_id,
        user_id=current_user.id, session_id=session.id,
        is_passed=1 if result.is_passed else 0,
        score_earned=result.score_earned, score_total=result.score_total,
        detail_json=_json.dumps(result.detail),
    )
    db.add(sub); db.commit()
    return ItemGradeResponse(is_passed=result.is_passed, score_earned=result.score_earned,
                             score_total=result.score_total, message=result.message)


def _sqllab_item_or_404(db, lab_id, item_id):
    item = db.query(LabItem).filter(LabItem.id == item_id, LabItem.lab_id == lab_id,
                                    LabItem.is_deleted == 0).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.kind != "sqllab":
        raise HTTPException(status_code=400, detail="Not a SQL-lab item")
    return item


@router.get("/{lab_id}/items/{item_id}/tasks", response_model=List[SqlLabTaskView])
def sqllab_item_tasks(lab_id: int, item_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    item = _sqllab_item_or_404(db, lab_id, item_id)
    tasks = (db.query(SqlLabTask).filter(SqlLabTask.sql_lab_question_id == item.ref_id,
                                         SqlLabTask.is_deleted == 0).order_by(SqlLabTask.order_index).all())
    return [SqlLabTaskView(id=t.id, title=t.title, description=t.description, order_index=t.order_index)
            for t in tasks]


@router.post("/{lab_id}/items/{item_id}/run", response_model=SqlLabRunResult)
def sqllab_item_run(lab_id: int, item_id: int, body: SqlLabRunRequest, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    item = _sqllab_item_or_404(db, lab_id, item_id)
    session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id, LabSession.user_id == current_user.id, LabSession.is_active == 1
    ).first()
    if not session:
        raise HTTPException(status_code=400, detail="No active session")
    try:
        db_path = ensure_sqllab_session(item.ref_id, session.id, item.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = execute_lab_query(db_path, body.query, timeout=15)
    return SqlLabRunResult(success=result["success"], columns=result["columns"], results=result["results"],
                           row_count=result["row_count"], error_message=result["error_message"])


def _sqllab_item_active_session(db, lab_id, current_user):
    session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id, LabSession.user_id == current_user.id, LabSession.is_active == 1
    ).first()
    if not session:
        raise HTTPException(status_code=400, detail="No active session")
    return session


@router.get("/{lab_id}/items/{item_id}/database", response_model=DatabaseState)
def sqllab_item_database(lab_id: int, item_id: int, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    item = _sqllab_item_or_404(db, lab_id, item_id)
    session = _sqllab_item_active_session(db, lab_id, current_user)
    try:
        db_path = ensure_sqllab_session(item.ref_id, session.id, item.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return DatabaseState(**introspect_db(db_path))


@router.post("/{lab_id}/items/{item_id}/reset", status_code=status.HTTP_204_NO_CONTENT)
def sqllab_item_reset(lab_id: int, item_id: int, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    item = _sqllab_item_or_404(db, lab_id, item_id)
    session = _sqllab_item_active_session(db, lab_id, current_user)
    try:
        reset_sqllab_session(session.id, item.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None


@router.get("/{lab_id}/item-progress", response_model=LabProgressResponse)
def lab_progress(lab_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    items = (db.query(LabItem).filter(LabItem.lab_id == lab_id, LabItem.is_deleted == 0)
             .order_by(LabItem.order_index).all())
    subs = db.query(LabSubmission).filter(
        LabSubmission.lab_id == lab_id, LabSubmission.user_id == current_user.id
    ).all()
    passed_items = {s.lab_item_id for s in subs if s.is_passed}
    rows, done = [], 0
    for it in items:
        is_passed = it.id in passed_items
        if is_passed:
            done += 1
        rows.append(LabItemProgress(lab_item_id=it.id, kind=it.kind, lab_task_id=None, is_passed=is_passed))
    return LabProgressResponse(lab_id=lab_id, done=done, total=len(items), items=rows)


@router.post("/{lab_id}/items/{item_id}/submission")
def submit_erd_item(
    lab_id: int, item_id: int,
    mode: str = Form(...),
    student_query: Optional[str] = Form(None),
    submission_xml_text: Optional[str] = Form(None),
    erd_img: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = db.query(LabItem).filter(LabItem.id == item_id, LabItem.lab_id == lab_id,
                                    LabItem.is_deleted == 0, LabItem.kind == "erd").first()
    if not item:
        raise HTTPException(status_code=404, detail="ERD item not found")
    session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id, LabSession.user_id == current_user.id, LabSession.is_active == 1
    ).first()
    if not session and current_user.role.value != "staff":
        raise HTTPException(status_code=400, detail="No active session")

    from app.models.er_diagram_question import ERDiagramQuestion
    from app.services.er_grading import stream_er_submission_grading
    from app.services.lab_erd_submission import stream_with_lab_item_persistence

    q = db.query(ERDiagramQuestion).filter(ERDiagramQuestion.id == item.ref_id,
                                           ERDiagramQuestion.is_deleted == 0).first()
    if not q:
        raise HTTPException(status_code=404, detail="ER question not found")

    grading = stream_er_submission_grading(
        question_id=q.id, problem_statement=q.problem_statement,
        difficulty_label=q.difficulty_label, rubric_json=q.rubric_json,
        submission_xml_text=(submission_xml_text or None), student_query=(student_query or None),
        erd_img=erd_img,
    )
    if mode == "Submit" and session is not None:
        grading = stream_with_lab_item_persistence(
            stream=grading, db=db, lab_id=lab_id, lab_item_id=item.id,
            user_id=current_user.id, session_id=session.id,
            submitted_xml=(submission_xml_text or None), submitted_image_storage_key=None,
        )
    return StreamingResponse(grading, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/submissions/{submission_id}/override", response_model=ItemGradeResponse)
def override_submission(submission_id: int, body: SubmissionOverrideRequest,
                        db: Session = Depends(get_db),
                        current_user: User = Depends(require_staff_role)):
    sub = db.query(LabSubmission).filter(LabSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub.override_score_earned = body.score_earned
    sub.override_score_total = body.score_total
    sub.override_reason = body.reason
    sub.overridden_by = current_user.id
    sub.overridden_at = datetime.utcnow()
    sub.is_passed = 1 if (body.score_earned / body.score_total) >= 0.5 else 0
    db.commit()
    return ItemGradeResponse(is_passed=bool(sub.is_passed), score_earned=body.score_earned,
                             score_total=body.score_total, message="Override applied")


@router.post("/session/{session_id}/execute", response_model=LabExecuteResponse)
def execute_query(
    session_id: int,
    execute_request: LabExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retired: the lab no longer owns a single shared session database.
    SQL-lab items run queries via POST /{lab_id}/items/{item_id}/run instead.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="The shared-DB session workspace was removed. "
               "Use POST /labs/{lab_id}/items/{item_id}/run for SQL-lab items."
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


@router.get("/{lab_id}/history", response_model=List[LabQueryHistoryResponse])
def get_lab_query_history(
    lab_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive query history for a user in a specific lab (Student/Staff).
    Returns all queries across all sessions (past and current) for this lab.
    Useful for reviewing learning progress when student re-enters a lab.
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

    # Query attempts with joined session and lab info
    from sqlalchemy import and_

    attempts_query = (
        db.query(
            LabAttempt.id,
            LabAttempt.lab_id,
            Lab.title.label("lab_title"),
            LabAttempt.session_id,
            LabSession.started_at.label("session_started_at"),
            LabSession.ended_at.label("session_ended_at"),
            LabAttempt.query,
            LabAttempt.success,
            LabAttempt.execution_time_ms,
            LabAttempt.row_count,
            LabAttempt.error_message,
            LabAttempt.submitted_at
        )
        .join(Lab, LabAttempt.lab_id == Lab.id)
        .join(LabSession, LabAttempt.session_id == LabSession.id)
        .filter(
            and_(
                LabAttempt.lab_id == lab_id,
                LabAttempt.user_id == current_user.id
            )
        )
        .order_by(LabAttempt.submitted_at.desc())
        .offset(skip)
        .limit(limit)
    )

    attempts = attempts_query.all()

    return [
        LabQueryHistoryResponse(
            id=attempt.id,
            lab_id=attempt.lab_id,
            lab_title=attempt.lab_title,
            session_id=attempt.session_id,
            session_started_at=attempt.session_started_at,
            session_ended_at=attempt.session_ended_at,
            query=attempt.query,
            success=bool(attempt.success),
            execution_time_ms=attempt.execution_time_ms,
            row_count=attempt.row_count,
            error_message=attempt.error_message,
            submitted_at=attempt.submitted_at
        )
        for attempt in attempts
    ]


@router.get("/history", response_model=List[LabQueryHistoryResponse])
def get_all_labs_query_history(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive query history for a user across all labs (Student/Staff).
    Returns all queries from all labs and all sessions.
    """
    # Query attempts with joined session and lab info
    attempts_query = (
        db.query(
            LabAttempt.id,
            LabAttempt.lab_id,
            Lab.title.label("lab_title"),
            LabAttempt.session_id,
            LabSession.started_at.label("session_started_at"),
            LabSession.ended_at.label("session_ended_at"),
            LabAttempt.query,
            LabAttempt.success,
            LabAttempt.execution_time_ms,
            LabAttempt.row_count,
            LabAttempt.error_message,
            LabAttempt.submitted_at
        )
        .join(Lab, LabAttempt.lab_id == Lab.id)
        .join(LabSession, LabAttempt.session_id == LabSession.id)
        .filter(LabAttempt.user_id == current_user.id)
        .order_by(LabAttempt.submitted_at.desc())
        .offset(skip)
        .limit(limit)
    )

    attempts = attempts_query.all()

    return [
        LabQueryHistoryResponse(
            id=attempt.id,
            lab_id=attempt.lab_id,
            lab_title=attempt.lab_title,
            session_id=attempt.session_id,
            session_started_at=attempt.session_started_at,
            session_ended_at=attempt.session_ended_at,
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
    Retired: the lab no longer owns a single shared session database.
    SQL-lab item databases are inspected via their own run endpoint.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="The shared-DB session workspace was removed."
    )


@router.post("/{lab_id}/session/reset")
def reset_session(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reset the per-(session, item) SQL-lab databases for the caller's active
    session, so the next run/submit re-copies each item's clean template.
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

    from app.utils.lab_cleanup import delete_session_file_with_retry
    from app.utils.sqllab_db_manager import get_sqllab_session_path

    items = db.query(LabItem).filter(
        LabItem.lab_id == lab_id, LabItem.kind == "sqllab", LabItem.is_deleted == 0
    ).all()
    for it in items:
        path = get_sqllab_session_path(session.id, it.id)
        if not delete_session_file_with_retry(path):
            logger.warning(f"Could not delete sql-lab session file during reset: {path}")

    return {"message": "Session databases reset successfully"}


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
    Retired: validated against the removed shared-DB section. SQL-lab items
    run via POST /{lab_id}/items/{item_id}/run and submit via .../submit.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="The shared-DB section was removed. Use the SQL-lab item run/submit endpoints."
    )


@router.post("/tasks/submit", response_model=LabTaskSubmitResponse)
def submit_task_answer(
    submit_request: LabTaskSubmitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Submit student's query result as an answer to a task (Student/Staff).
    Hashes the result and compares against task's correct hash.
    Saves submission record regardless of correctness.
    """
    # 1. Get task and verify it has an answer
    task = db.query(LabTask).filter(
        LabTask.id == submit_request.task_id,
        LabTask.is_deleted == 0
    ).first()

    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found"
        )

    if not task.correct_answer_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task does not have an answer assigned yet"
        )

    # 2. Get session and verify ownership + active
    session = db.query(LabSession).filter(
        LabSession.id == submit_request.session_id,
        LabSession.user_id == current_user.id,
        LabSession.is_active == 1
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active session not found"
        )

    # 3. Verify session belongs to the same lab as the task
    if session.lab_id != task.lab_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task does not belong to this lab session"
        )

    # 4. Generate hash from submitted results
    # Convert dict results to tuple format for hash generation
    results_tuples = [
        tuple(row[col] for col in submit_request.columns)
        for row in submit_request.results
    ]
    submitted_hash = generate_hash(results_tuples, submit_request.columns)

    # 5. Compare hashes
    is_correct = submitted_hash == task.correct_answer_hash

    # 6. Save submission
    submission = LabTaskSubmission(
        task_id=submit_request.task_id,
        user_id=current_user.id,
        session_id=submit_request.session_id,
        lab_id=session.lab_id,
        submitted_query=submit_request.query,
        submitted_result_hash=submitted_hash,
        is_correct=1 if is_correct else 0,
        execution_time_ms=submit_request.execution_time_ms,
        row_count=submit_request.row_count
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    # 7. Return result
    message = (
        "Correct! Your query produces the expected result." if is_correct
        else "Incorrect. Your query result doesn't match the expected answer."
    )

    return LabTaskSubmitResponse(
        submission_id=submission.id,
        is_correct=is_correct,
        message=message,
        submitted_at=submission.submitted_at
    )


@router.get("/{lab_id}/progress", response_model=LabTaskProgressResponse)
def get_lab_task_progress(
    lab_id: int,
    student_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get student's task progress for a lab (Student/Staff).
    Returns progress for all tasks: is_completed, attempt_count, last_submitted_at.

    For staff: Can optionally pass student_id to fetch a specific student's progress.
    """
    # If fetching for a specific student, require staff role
    if student_id and current_user.role != "staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff only"
        )

    # Determine which user's progress to fetch
    target_user_id = student_id if student_id else current_user.id

    # Verify lab exists
    lab = db.query(Lab).filter(Lab.id == lab_id, Lab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Get all tasks for this lab
    tasks = db.query(LabTask).filter(
        LabTask.lab_id == lab_id,
        LabTask.is_deleted == 0
    ).order_by(LabTask.order_index, LabTask.created_at).all()

    # For each task, get submission statistics
    task_progress_list = []
    for task in tasks:
        # Get all submissions for this task by target user
        submissions = db.query(LabTaskSubmission).filter(
            LabTaskSubmission.task_id == task.id,
            LabTaskSubmission.user_id == target_user_id
        ).all()

        # Calculate progress
        attempt_count = len(submissions)
        is_completed = any(sub.is_correct == 1 for sub in submissions)
        last_submitted_at = max(
            (sub.submitted_at for sub in submissions),
            default=None
        )

        task_progress_list.append(
            LabTaskProgress(
                task_id=task.id,
                is_completed=is_completed,
                attempt_count=attempt_count,
                last_submitted_at=last_submitted_at
            )
        )

    return LabTaskProgressResponse(tasks=task_progress_list)


# ==============================================================================
# Task 13: Staff monitoring endpoints
# ==============================================================================

@router.get("/{lab_id}/students", response_model=LabStudentsResponse)
def lab_students(lab_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(require_staff_role)):
    total_items = db.query(LabItem).filter(LabItem.lab_id == lab_id, LabItem.is_deleted == 0).count()
    rows = (db.query(LabSubmission, User.email).join(User, LabSubmission.user_id == User.id)
            .filter(LabSubmission.lab_id == lab_id).all())
    agg: dict[int, dict] = defaultdict(lambda: {"email": "", "passed": set(), "last": None})
    for sub, email in rows:
        a = agg[sub.user_id]
        a["email"] = email
        if sub.is_passed:
            a["passed"].add(sub.lab_item_id)
        if a["last"] is None or sub.submitted_at > a["last"]:
            a["last"] = sub.submitted_at
    students = [LabStudentSummary(user_id=uid, email=a["email"], passed_items=len(a["passed"]),
                                  total_items=total_items, last_submitted_at=a["last"])
                for uid, a in agg.items()]
    return LabStudentsResponse(lab_id=lab_id, total_items=total_items, students=students)


@router.get("/{lab_id}/submissions", response_model=List[LabSubmissionView])
def lab_submissions(lab_id: int, student_id: Optional[int] = None, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    is_staff = current_user.role.value == "staff"
    if not is_staff and student_id is not None and student_id != current_user.id:
        raise HTTPException(status_code=403, detail="Students can only view their own submissions")
    target = student_id if (is_staff and student_id) else current_user.id
    rows = (db.query(LabSubmission, LabItem).join(LabItem, LabSubmission.lab_item_id == LabItem.id)
            .filter(LabSubmission.lab_id == lab_id, LabSubmission.user_id == target)
            .order_by(LabSubmission.submitted_at.desc()).all())
    out: list[LabSubmissionView] = []
    for sub, item in rows:
        try:
            title = get_handler(item.kind).to_view(db, item.ref_id).title
        except ValueError:
            title = "(unavailable)"
        out.append(LabSubmissionView(
            id=sub.id, lab_item_id=sub.lab_item_id, kind=item.kind, item_title=title,
            is_passed=bool(sub.is_passed), score_earned=sub.score_earned, score_total=sub.score_total,
            override_score_earned=sub.override_score_earned, override_score_total=sub.override_score_total,
            submitted_at=sub.submitted_at))
    return out


@router.get("/{lab_id}/student-attempts", response_model=LabStudentAttemptsResponse)
def get_student_attempts(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Get aggregated student attempts for all tasks in a lab (Staff only).
    Returns per-student summary: correct, incorrect, not attempted counts.
    """
    # Verify lab exists
    lab = db.query(Lab).filter(Lab.id == lab_id, Lab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lab not found"
        )

    # Get total task count
    total_tasks = db.query(LabTask).filter(
        LabTask.lab_id == lab_id,
        LabTask.is_deleted == 0
    ).count()

    # Get all students who have submitted to this lab
    # Aggregate: correct count, incorrect count, attempted tasks
    from sqlalchemy import func, case

    student_data = db.query(
        LabTaskSubmission.user_id,
        User.email,
        func.count(func.distinct(
            case((LabTaskSubmission.is_correct == 1, LabTaskSubmission.task_id))
        )).label('correct_count'),
        func.max(LabTaskSubmission.submitted_at).label('last_submission_at')
    ).join(
        User, LabTaskSubmission.user_id == User.id
    ).filter(
        LabTaskSubmission.lab_id == lab_id
    ).group_by(
        LabTaskSubmission.user_id,
        User.email
    ).order_by(
        func.max(LabTaskSubmission.submitted_at).desc()
    ).all()

    # Build response
    students = []
    for row in student_data:
        # Calculate counts:
        # - correct_count: unique tasks with at least one correct submission
        # - not_solved_count: total tasks - correct (includes incorrect + not attempted)
        not_solved = total_tasks - row.correct_count

        students.append(StudentAttemptSummary(
            user_id=row.user_id,
            email=row.email,
            correct_count=row.correct_count,
            not_solved_count=not_solved,
            total_tasks=total_tasks,
            last_submission_at=row.last_submission_at
        ))

    return LabStudentAttemptsResponse(
        lab_id=lab_id,
        lab_title=lab.title,
        total_tasks=total_tasks,
        students=students
    )


@router.get("/{lab_id}/students/{student_id}/history", response_model=List[LabQueryHistoryResponse])
def get_student_query_history(
    lab_id: int,
    student_id: int,
    skip: int = 0,
    limit: int = 1000,  # Higher limit for comprehensive review
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role)
):
    """
    Get comprehensive query history for a specific student in a lab (Staff only).
    Returns all queries across all sessions in chronological order for review purposes.
    Staff use this to understand student's problem-solving approach and progression.
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

    # Verify student exists and is a student role
    student = db.query(User).filter(User.id == student_id).first()

    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )

    if student.role != "student":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a student"
        )

    # Query attempts with joined session and lab info
    from sqlalchemy import and_

    attempts_query = (
        db.query(
            LabAttempt.id,
            LabAttempt.lab_id,
            Lab.title.label("lab_title"),
            LabAttempt.session_id,
            LabSession.started_at.label("session_started_at"),
            LabSession.ended_at.label("session_ended_at"),
            LabAttempt.query,
            LabAttempt.success,
            LabAttempt.execution_time_ms,
            LabAttempt.row_count,
            LabAttempt.error_message,
            LabAttempt.submitted_at,
            User.email.label("student_email")
        )
        .join(Lab, LabAttempt.lab_id == Lab.id)
        .join(LabSession, LabAttempt.session_id == LabSession.id)
        .join(User, LabAttempt.user_id == User.id)
        .filter(
            and_(
                LabAttempt.lab_id == lab_id,
                LabAttempt.user_id == student_id
            )
        )
        .order_by(LabAttempt.submitted_at.asc())  # Chronological order for review
        .offset(skip)
        .limit(limit)
    )

    attempts = attempts_query.all()

    return [
        LabQueryHistoryResponse(
            id=attempt.id,
            lab_id=attempt.lab_id,
            lab_title=attempt.lab_title,
            session_id=attempt.session_id,
            session_started_at=attempt.session_started_at,
            session_ended_at=attempt.session_ended_at,
            query=attempt.query,
            success=bool(attempt.success),
            execution_time_ms=attempt.execution_time_ms,
            row_count=attempt.row_count,
            error_message=attempt.error_message,
            submitted_at=attempt.submitted_at,
            student_email=attempt.student_email
        )
        for attempt in attempts
    ]
