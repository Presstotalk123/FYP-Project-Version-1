from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, ensure_owner_or_staff
from app.models.user import User
from app.models.sql_lab_question import SqlLabQuestion, SqlLabTask
from app.schemas.sql_lab_question import (
    SqlLabQuestionCreate, SqlLabQuestionResponse, SqlLabTaskView,
    SqlLabQuestionListItem, SqlLabPracticeSubmit,
    SqlLabTaskShellCreate, SqlLabTaskUpdate, SqlLabTaskAssign,
    SqlLabReorderRequest, SqlLabMetaUpdate, SqlLabSeedUpdate,
)
from app.schemas.lab import SqlLabRunRequest, SqlLabRunResult, ItemGradeResponse, DatabaseState, SeedRebuildResult
from app.utils.sqllab_db_manager import (
    create_sqllab_template, get_sqllab_template_path, ensure_sqllab_practice_session,
    reset_sqllab_practice, introspect_db,
)
from app.utils.lab_db_manager import LabDatabaseError
from app.core.lab_query_executor import execute_lab_query
from app.core.answer_validator import hash_run_result
from app.services.lab_refs import running_labs_referencing
from app.services import question_authoring as qa
from app.services.question_authoring import SQLLAB_ADAPTER

router = APIRouter(prefix="/sql-lab-questions", tags=["sql-lab-questions"])


def _to_response(q: SqlLabQuestion, tasks: list[SqlLabTask]) -> SqlLabQuestionResponse:
    return SqlLabQuestionResponse(
        id=q.id, title=q.title, description=q.description, difficulty=q.difficulty.value,
        status=q.status, schema_sql=q.schema_sql, sample_data_sql=q.sample_data_sql,
        created_by=q.created_by, created_at=q.created_at,
        tasks=[SqlLabTaskView(id=t.id, title=t.title, description=t.description,
                              order_index=t.order_index, has_answer=t.correct_answer_hash is not None)
               for t in tasks],
    )


@router.post("", response_model=SqlLabQuestionResponse, status_code=status.HTTP_201_CREATED)
def create_sql_lab_question(data: SqlLabQuestionCreate, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    q = qa.create_draft(db, SQLLAB_ADAPTER, title=data.title, description=data.description,
                        difficulty=data.difficulty,
                        seed={"schema_sql": data.schema_sql, "sample_data_sql": data.sample_data_sql},
                        created_by=current_user.id)
    if data.tasks:  # legacy bulk path: create + hash + auto-finalize
        for t in data.tasks:
            task = qa.add_task(db, SQLLAB_ADAPTER, q, title=t.title, description=t.description)
            qa.assign_answer(db, SQLLAB_ADAPTER, q, task, query=t.correct_query)
        qa.finalize(db, SQLLAB_ADAPTER, q)
    return _to_response(q, qa.list_tasks(db, SQLLAB_ADAPTER, q.id))


@router.get("", response_model=List[SqlLabQuestionListItem])
def list_sql_lab_questions(status_filter: str | None = Query(default=None, alias="status"),
                           mine: bool = False,
                           db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = (db.query(SqlLabQuestion, func.count(SqlLabTask.id))
             .outerjoin(SqlLabTask, (SqlLabTask.sql_lab_question_id == SqlLabQuestion.id)
                        & (SqlLabTask.is_deleted == 0))
             .filter(SqlLabQuestion.is_deleted == 0))
    if status_filter:
        query = query.filter(SqlLabQuestion.status == status_filter)
    if mine:
        query = query.filter(SqlLabQuestion.created_by == current_user.id)
    rows = query.group_by(SqlLabQuestion.id).order_by(SqlLabQuestion.created_at.desc()).all()
    return [SqlLabQuestionListItem(id=q.id, title=q.title, difficulty=q.difficulty.value,
                                   status=q.status, task_count=n, created_by=q.created_by,
                                   created_at=q.created_at)
            for q, n in rows]


def _load_or_404(db: Session, qid: int) -> SqlLabQuestion:
    q = db.query(SqlLabQuestion).filter(SqlLabQuestion.id == qid, SqlLabQuestion.is_deleted == 0).first()
    if not q:
        raise HTTPException(status_code=404, detail="SQL-lab question not found")
    return q


@router.get("/{qid}", response_model=SqlLabQuestionResponse)
def get_sql_lab_question(qid: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    tasks = (db.query(SqlLabTask).filter(SqlLabTask.sql_lab_question_id == qid, SqlLabTask.is_deleted == 0)
             .order_by(SqlLabTask.order_index).all())
    return _to_response(q, tasks)


@router.delete("/{qid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sql_lab_question(qid: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    refs = running_labs_referencing(db, "sqllab", qid)
    if refs:
        raise HTTPException(status_code=409, detail=f"In use by running lab(s): {', '.join(refs)}")
    q.is_deleted = 1
    for t in db.query(SqlLabTask).filter(SqlLabTask.sql_lab_question_id == qid).all():
        t.is_deleted = 1
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Two-phase authoring endpoints
# ---------------------------------------------------------------------------

@router.post("/{qid}/tasks", response_model=SqlLabQuestionResponse)
def add_task(qid: int, body: SqlLabTaskShellCreate, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, SQLLAB_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, SQLLAB_ADAPTER, q)
    qa.add_task(db, SQLLAB_ADAPTER, q, title=body.title, description=body.description)
    return _to_response(q, qa.list_tasks(db, SQLLAB_ADAPTER, qid))


def _load_task(db, qid: int, task_id: int) -> SqlLabTask:
    t = db.query(SqlLabTask).filter(SqlLabTask.id == task_id,
                                    SqlLabTask.sql_lab_question_id == qid,
                                    SqlLabTask.is_deleted == 0).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return t


@router.post("/{qid}/tasks/{task_id}/assign", response_model=SqlLabQuestionResponse)
def assign_answer(qid: int, task_id: int, body: SqlLabTaskAssign, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, SQLLAB_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, SQLLAB_ADAPTER, q)
    qa.assign_answer(db, SQLLAB_ADAPTER, q, _load_task(db, qid, task_id), query=body.query)
    return _to_response(q, qa.list_tasks(db, SQLLAB_ADAPTER, qid))


@router.put("/{qid}/tasks/reorder", response_model=SqlLabQuestionResponse)
def reorder(qid: int, body: SqlLabReorderRequest, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, SQLLAB_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, SQLLAB_ADAPTER, q)
    qa.reorder_tasks(db, SQLLAB_ADAPTER, q, body.ordered_ids)
    return _to_response(q, qa.list_tasks(db, SQLLAB_ADAPTER, qid))


@router.put("/{qid}/tasks/{task_id}", response_model=SqlLabQuestionResponse)
def update_task(qid: int, task_id: int, body: SqlLabTaskUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, SQLLAB_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.update_task(db, _load_task(db, qid, task_id), title=body.title, description=body.description)
    return _to_response(q, qa.list_tasks(db, SQLLAB_ADAPTER, qid))


@router.delete("/{qid}/tasks/{task_id}", response_model=SqlLabQuestionResponse)
def delete_task(qid: int, task_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, SQLLAB_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, SQLLAB_ADAPTER, q)
    qa.soft_delete_task(db, _load_task(db, qid, task_id))
    return _to_response(q, qa.list_tasks(db, SQLLAB_ADAPTER, qid))


@router.patch("/{qid}", response_model=SqlLabQuestionResponse)
def update_meta(qid: int, body: SqlLabMetaUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, SQLLAB_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    if body.title is not None:
        q.title = body.title
    if body.description is not None:
        q.description = body.description
    if body.difficulty is not None:
        q.difficulty = body.difficulty
    db.commit()
    db.refresh(q)
    return _to_response(q, qa.list_tasks(db, SQLLAB_ADAPTER, qid))


@router.put("/{qid}/seed", response_model=SeedRebuildResult)
def update_seed(qid: int, body: SqlLabSeedUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, SQLLAB_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, SQLLAB_ADAPTER, q)
    return qa.rebuild_seed(db, SQLLAB_ADAPTER, q,
                           {"schema_sql": body.schema_sql, "sample_data_sql": body.sample_data_sql})


@router.post("/{qid}/finalize", response_model=SqlLabQuestionResponse)
def finalize(qid: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, SQLLAB_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.finalize(db, SQLLAB_ADAPTER, q)
    return _to_response(q, qa.list_tasks(db, SQLLAB_ADAPTER, qid))


# ---------------------------------------------------------------------------
# Standalone "practice" solving (any authenticated user, outside any lab).
# Same grading as the in-lab path, but keyed to a per-(question, user) writable DB.
# ---------------------------------------------------------------------------

@router.post("/{qid}/run", response_model=SqlLabRunResult)
def run_sql_lab_practice(qid: int, body: SqlLabRunRequest, db: Session = Depends(get_db),
                         current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    try:
        db_path = ensure_sqllab_practice_session(q.id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SqlLabRunResult.from_executor(execute_lab_query(db_path, body.query, timeout=15))


@router.post("/{qid}/submit", response_model=ItemGradeResponse)
def submit_sql_lab_practice(qid: int, body: SqlLabPracticeSubmit, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    task = db.query(SqlLabTask).filter(
        SqlLabTask.id == body.task_id, SqlLabTask.sql_lab_question_id == q.id, SqlLabTask.is_deleted == 0
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.correct_answer_hash:
        return ItemGradeResponse(is_passed=False, message="Task has no assigned answer")
    try:
        db_path = ensure_sqllab_practice_session(q.id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = execute_lab_query(db_path, body.query, timeout=15)
    if not result["success"]:
        return ItemGradeResponse(is_passed=False, message=result["error_message"] or "Query failed")
    passed = hash_run_result(result) == task.correct_answer_hash
    return ItemGradeResponse(is_passed=passed, message="Correct" if passed else "Incorrect result")


@router.get("/{qid}/database", response_model=DatabaseState)
def sql_lab_practice_database(qid: int, db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    try:
        db_path = ensure_sqllab_practice_session(q.id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return DatabaseState(**introspect_db(db_path))


@router.post("/{qid}/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_sql_lab_practice_db(qid: int, db: Session = Depends(get_db),
                              current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    try:
        reset_sqllab_practice(q.id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None
