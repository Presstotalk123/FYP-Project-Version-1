from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_staff_role, get_current_user
from app.models.user import User
from app.models.sql_lab_question import SqlLabQuestion, SqlLabTask
from app.schemas.sql_lab_question import (
    SqlLabQuestionCreate, SqlLabQuestionResponse, SqlLabTaskView,
    SqlLabQuestionListItem, SqlLabPracticeSubmit,
)
from app.schemas.lab import SqlLabRunRequest, SqlLabRunResult, ItemGradeResponse, DatabaseState
from app.utils.sqllab_db_manager import (
    create_sqllab_template, get_sqllab_template_path, ensure_sqllab_practice_session,
    reset_sqllab_practice, introspect_db,
)
from app.utils.lab_db_manager import LabDatabaseError
from app.core.lab_query_executor import execute_lab_query
from app.core.answer_validator import generate_hash
from app.services.lab_refs import labs_referencing

router = APIRouter(prefix="/sql-lab-questions", tags=["sql-lab-questions"])


def _to_response(q: SqlLabQuestion, tasks: list[SqlLabTask]) -> SqlLabQuestionResponse:
    return SqlLabQuestionResponse(
        id=q.id, title=q.title, description=q.description, difficulty=q.difficulty.value,
        schema_sql=q.schema_sql, sample_data_sql=q.sample_data_sql,
        created_by=q.created_by, created_at=q.created_at,
        tasks=[SqlLabTaskView(id=t.id, title=t.title, description=t.description,
                              order_index=t.order_index, has_answer=t.correct_answer_hash is not None)
               for t in tasks],
    )


@router.post("", response_model=SqlLabQuestionResponse, status_code=status.HTTP_201_CREATED)
def create_sql_lab_question(
    data: SqlLabQuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    q = SqlLabQuestion(
        title=data.title, description=data.description, difficulty=data.difficulty,
        schema_sql=data.schema_sql, sample_data_sql=data.sample_data_sql,
        created_by=current_user.id, is_deleted=0,
    )
    db.add(q)
    db.flush()  # get q.id

    # Build the template DB from schema + seed
    try:
        create_sqllab_template(q.id, data.schema_sql, data.sample_data_sql)
        q.template_db_path = f"sqllab_q_{q.id}_template.db"
    except LabDatabaseError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to build question database: {str(e)}")

    # Create tasks and assign each answer hash by running its correct query on the template
    template_path = get_sqllab_template_path(q.id)
    tasks: list[SqlLabTask] = []
    for idx, t in enumerate(data.tasks):
        result = execute_lab_query(template_path, t.correct_query, timeout=15)
        if not result["success"]:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Task {idx + 1} ({t.title}) correct query failed: {result['error_message']}",
            )
        results_tuples = [tuple(row[col] for col in result["columns"]) for row in result["results"]]
        task = SqlLabTask(
            sql_lab_question_id=q.id, title=t.title, description=t.description, order_index=idx,
            correct_query=t.correct_query, correct_answer_hash=generate_hash(results_tuples, result["columns"]),
        )
        db.add(task)
        tasks.append(task)

    db.commit()
    db.refresh(q)
    for t in tasks:
        db.refresh(t)
    return _to_response(q, tasks)


@router.get("", response_model=List[SqlLabQuestionListItem])
def list_sql_lab_questions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    qs = db.query(SqlLabQuestion).filter(SqlLabQuestion.is_deleted == 0).order_by(SqlLabQuestion.created_at.desc()).all()
    out = []
    for q in qs:
        n = db.query(SqlLabTask).filter(SqlLabTask.sql_lab_question_id == q.id, SqlLabTask.is_deleted == 0).count()
        out.append(SqlLabQuestionListItem(id=q.id, title=q.title, difficulty=q.difficulty.value,
                                          task_count=n, created_by=q.created_by, created_at=q.created_at))
    return out


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
def delete_sql_lab_question(qid: int, db: Session = Depends(get_db), current_user: User = Depends(require_staff_role)):
    q = _load_or_404(db, qid)
    refs = labs_referencing(db, "sqllab", qid)
    if refs:
        raise HTTPException(status_code=409, detail=f"In use by lab(s): {', '.join(refs)}")
    q.is_deleted = 1
    for t in db.query(SqlLabTask).filter(SqlLabTask.sql_lab_question_id == qid).all():
        t.is_deleted = 1
    db.commit()
    return None


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
    result = execute_lab_query(db_path, body.query, timeout=15)
    return SqlLabRunResult(success=result["success"], columns=result["columns"], results=result["results"],
                           row_count=result["row_count"], error_message=result["error_message"])


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
    results_tuples = [tuple(row[col] for col in result["columns"]) for row in result["results"]]
    passed = generate_hash(results_tuples, result["columns"]) == task.correct_answer_hash
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
