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
from app.models.lab_item import LabItem
from app.models.lab_submission import LabSubmission
from app.core.security import hash_password, verify_password
from app.services.lab_items.registry import get_handler, HANDLERS
from collections import defaultdict
from app.schemas.lab import (
    LabUpdate, LabListItem, LabResponse,
    SessionResponse, StopLabResponse,
    UnifiedLabCreate, LabItemCreate, LabItemResponse, LabReorderRequest,
    UnifiedLabDetail, JoinLabRequest, SqlItemSubmit, ItemGradeResponse,
    LabItemProgress, LabProgressResponse, SubmissionOverrideRequest,
    LabStudentSummary, LabStudentsResponse, LabSubmissionView,
)
from app.dependencies import get_current_user, require_staff_role
from app.utils.lab_db_manager import (
    delete_lab_template, get_lab_template_path, get_schema_info, LabDatabaseError
)
from app.utils.lab_cleanup import terminate_all_lab_sessions
from app.core.lab_query_executor import execute_lab_query
from app.core.answer_validator import generate_hash
from app.utils.sqllab_db_manager import ensure_sqllab_session, reset_sqllab_session, introspect_db
from app.utils.graph_db_manager import ensure_graph_session, reset_graph_session, get_graph_schema_info
from app.core.graph_query_executor import execute_graph_query
from app.schemas.lab import SqlLabRunRequest, SqlLabRunResult, DatabaseState

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
    if body.kind in ("sql", "erd", "sqllab", "graph"):
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
    is_staff = current_user.role.value in ("staff", "admin")
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
    db.add(session)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent join won the race (partial unique index on active sessions);
        # resume that session instead of returning a 500.
        db.rollback()
        existing = db.query(LabSession).filter(
            LabSession.lab_id == lab_id, LabSession.user_id == current_user.id,
            LabSession.is_active == 1
        ).first()
        if existing:
            return existing
        raise
    db.refresh(session)
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
    """A lab item solved in a query workspace — SQL-lab or graph (Cypher)."""
    item = db.query(LabItem).filter(LabItem.id == item_id, LabItem.lab_id == lab_id,
                                    LabItem.is_deleted == 0).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if item.kind not in ("sqllab", "graph"):
        raise HTTPException(status_code=400, detail="Not a runnable workspace item")
    return item


def _graph_database_state(db_path: str) -> DatabaseState:
    """Adapt the rich graph schema (node labels + relationship types as tables) to the
    lean DatabaseState the workspace renders."""
    info = get_graph_schema_info(db_path)
    return DatabaseState(tables=[
        {
            "name": t["name"],
            "columns": [{"name": c["name"], "type": c["type"]} for c in t["columns"]],
            "row_count": t["row_count"],
            "sample_rows": (t.get("sample_data") or {}).get("rows", []),
        }
        for t in info["tables"]
    ])


def _sqllab_item_active_session(db, lab_id, current_user):
    session = db.query(LabSession).filter(
        LabSession.lab_id == lab_id, LabSession.user_id == current_user.id, LabSession.is_active == 1
    ).first()
    if not session:
        raise HTTPException(status_code=400, detail="No active session")
    return session


@router.post("/{lab_id}/items/{item_id}/run", response_model=SqlLabRunResult)
def sqllab_item_run(lab_id: int, item_id: int, body: SqlLabRunRequest, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    item = _sqllab_item_or_404(db, lab_id, item_id)
    session = _sqllab_item_active_session(db, lab_id, current_user)
    try:
        if item.kind == "graph":
            db_path = ensure_graph_session(item.ref_id, session.id, item.id)
            return SqlLabRunResult.from_executor(execute_graph_query(db_path, body.query, timeout=15))
        db_path = ensure_sqllab_session(item.ref_id, session.id, item.id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SqlLabRunResult.from_executor(execute_lab_query(db_path, body.query, timeout=15))


@router.get("/{lab_id}/items/{item_id}/database", response_model=DatabaseState)
def sqllab_item_database(lab_id: int, item_id: int, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    item = _sqllab_item_or_404(db, lab_id, item_id)
    session = _sqllab_item_active_session(db, lab_id, current_user)
    try:
        if item.kind == "graph":
            db_path = ensure_graph_session(item.ref_id, session.id, item.id)
            return _graph_database_state(db_path)
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
        if item.kind == "graph":
            reset_graph_session(session.id, item.id)
        else:
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
    if not session and current_user.role.value not in ("staff", "admin"):
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
    if body.score_earned > body.score_total:
        raise HTTPException(status_code=400, detail="score_earned cannot exceed score_total")
    sub.override_score_earned = body.score_earned
    sub.override_score_total = body.score_total
    sub.override_reason = body.reason
    sub.overridden_by = current_user.id
    sub.overridden_at = datetime.utcnow()
    sub.is_passed = 1 if (body.score_earned / body.score_total) >= 0.5 else 0
    db.commit()
    return ItemGradeResponse(is_passed=bool(sub.is_passed), score_earned=body.score_earned,
                             score_total=body.score_total, message="Override applied")


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
    from app.utils.graph_db_manager import get_graph_session_path

    items = db.query(LabItem).filter(
        LabItem.lab_id == lab_id, LabItem.kind.in_(("sqllab", "graph")), LabItem.is_deleted == 0
    ).all()
    for it in items:
        path = (get_graph_session_path(session.id, it.id) if it.kind == "graph"
                else get_sqllab_session_path(session.id, it.id))
        if not delete_session_file_with_retry(path):
            logger.warning(f"Could not delete {it.kind} session file during reset: {path}")

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
    is_staff = current_user.role.value in ("staff", "admin")
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
