from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, ensure_owner_or_staff
from app.models.user import User
from app.models.graph_question import GraphQuestion, GraphTask
from app.schemas.graph_question import (
    GraphQuestionCreate, GraphQuestionResponse, GraphTaskView,
    GraphQuestionListItem, GraphPracticeSubmit,
    GraphTaskShellCreate, GraphTaskUpdate, GraphTaskAssign,
    GraphReorderRequest, GraphMetaUpdate, GraphSeedUpdate,
)
from app.schemas.lab import SqlLabRunRequest, SqlLabRunResult, ItemGradeResponse, DatabaseStateResponse, SeedRebuildResult
from app.utils.graph_db_manager import (
    create_graph_template, get_graph_template_path, ensure_graph_practice_session,
    reset_graph_practice, get_graph_schema_info,
)
from app.utils.lab_db_manager import LabDatabaseError
from app.core.graph_query_executor import execute_graph_query
from app.core.answer_validator import hash_run_result
from app.services.lab_refs import running_labs_referencing
from app.services import question_authoring as qa
from app.services.question_authoring import GRAPH_ADAPTER

router = APIRouter(prefix="/graph-questions", tags=["graph-questions"])


def _to_response(q: GraphQuestion, tasks: list[GraphTask]) -> GraphQuestionResponse:
    return GraphQuestionResponse(
        id=q.id, title=q.title, description=q.description, difficulty=q.difficulty.value,
        status=q.status, seed_cypher=q.seed_cypher,
        created_by=q.created_by, created_at=q.created_at,
        tasks=[GraphTaskView(id=t.id, title=t.title, description=t.description,
                             order_index=t.order_index, has_answer=t.correct_answer_hash is not None)
               for t in tasks],
    )


@router.post("", response_model=GraphQuestionResponse, status_code=status.HTTP_201_CREATED)
def create_graph_question(data: GraphQuestionCreate, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    q = qa.create_draft(db, GRAPH_ADAPTER, title=data.title, description=data.description,
                        difficulty=data.difficulty,
                        seed={"seed_cypher": data.seed_cypher},
                        created_by=current_user.id)
    if data.tasks:  # legacy bulk path: create + hash + auto-finalize
        for t in data.tasks:
            task = qa.add_task(db, GRAPH_ADAPTER, q, title=t.title, description=t.description)
            qa.assign_answer(db, GRAPH_ADAPTER, q, task, query=t.correct_query)
        qa.finalize(db, GRAPH_ADAPTER, q)
    return _to_response(q, qa.list_tasks(db, GRAPH_ADAPTER, q.id))


@router.get("", response_model=List[GraphQuestionListItem])
def list_graph_questions(status_filter: str | None = Query(default=None, alias="status"),
                         mine: bool = False,
                         db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = (db.query(GraphQuestion, func.count(GraphTask.id))
             .outerjoin(GraphTask, (GraphTask.graph_question_id == GraphQuestion.id)
                        & (GraphTask.is_deleted == 0))
             .filter(GraphQuestion.is_deleted == 0))
    if status_filter:
        query = query.filter(GraphQuestion.status == status_filter)
    if mine:
        query = query.filter(GraphQuestion.created_by == current_user.id)
    rows = query.group_by(GraphQuestion.id).order_by(GraphQuestion.created_at.desc()).all()
    return [GraphQuestionListItem(id=q.id, title=q.title, difficulty=q.difficulty.value,
                                  status=q.status, task_count=n, created_by=q.created_by,
                                  created_at=q.created_at)
            for q, n in rows]


def _load_or_404(db: Session, qid: int) -> GraphQuestion:
    q = db.query(GraphQuestion).filter(GraphQuestion.id == qid, GraphQuestion.is_deleted == 0).first()
    if not q:
        raise HTTPException(status_code=404, detail="Graph question not found")
    return q


@router.get("/{qid}", response_model=GraphQuestionResponse)
def get_graph_question(qid: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    tasks = (db.query(GraphTask).filter(GraphTask.graph_question_id == qid, GraphTask.is_deleted == 0)
             .order_by(GraphTask.order_index).all())
    return _to_response(q, tasks)


@router.delete("/{qid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_graph_question(qid: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    refs = running_labs_referencing(db, "graph", qid)
    if refs:
        raise HTTPException(status_code=409, detail=f"In use by running lab(s): {', '.join(refs)}")
    q.is_deleted = 1
    for t in db.query(GraphTask).filter(GraphTask.graph_question_id == qid).all():
        t.is_deleted = 1
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Two-phase authoring endpoints
# ---------------------------------------------------------------------------

@router.post("/{qid}/tasks", response_model=GraphQuestionResponse)
def add_task(qid: int, body: GraphTaskShellCreate, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, GRAPH_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, GRAPH_ADAPTER, q)
    qa.add_task(db, GRAPH_ADAPTER, q, title=body.title, description=body.description)
    return _to_response(q, qa.list_tasks(db, GRAPH_ADAPTER, qid))


def _load_task(db, qid: int, task_id: int) -> GraphTask:
    t = db.query(GraphTask).filter(GraphTask.id == task_id,
                                   GraphTask.graph_question_id == qid,
                                   GraphTask.is_deleted == 0).first()
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return t


@router.post("/{qid}/tasks/{task_id}/assign", response_model=GraphQuestionResponse)
def assign_answer(qid: int, task_id: int, body: GraphTaskAssign, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, GRAPH_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, GRAPH_ADAPTER, q)
    qa.assign_answer(db, GRAPH_ADAPTER, q, _load_task(db, qid, task_id), query=body.query)
    return _to_response(q, qa.list_tasks(db, GRAPH_ADAPTER, qid))


@router.put("/{qid}/tasks/reorder", response_model=GraphQuestionResponse)
def reorder(qid: int, body: GraphReorderRequest, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, GRAPH_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, GRAPH_ADAPTER, q)
    qa.reorder_tasks(db, GRAPH_ADAPTER, q, body.ordered_ids)
    return _to_response(q, qa.list_tasks(db, GRAPH_ADAPTER, qid))


@router.put("/{qid}/tasks/{task_id}", response_model=GraphQuestionResponse)
def update_task(qid: int, task_id: int, body: GraphTaskUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, GRAPH_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.update_task(db, _load_task(db, qid, task_id), title=body.title, description=body.description)
    return _to_response(q, qa.list_tasks(db, GRAPH_ADAPTER, qid))


@router.delete("/{qid}/tasks/{task_id}", response_model=GraphQuestionResponse)
def delete_task(qid: int, task_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, GRAPH_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, GRAPH_ADAPTER, q)
    qa.soft_delete_task(db, _load_task(db, qid, task_id))
    return _to_response(q, qa.list_tasks(db, GRAPH_ADAPTER, qid))


@router.patch("/{qid}", response_model=GraphQuestionResponse)
def update_meta(qid: int, body: GraphMetaUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, GRAPH_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    if body.title is not None:
        q.title = body.title
    if body.description is not None:
        q.description = body.description
    if body.difficulty is not None:
        q.difficulty = body.difficulty
    db.commit()
    db.refresh(q)
    return _to_response(q, qa.list_tasks(db, GRAPH_ADAPTER, qid))


@router.put("/{qid}/seed", response_model=SeedRebuildResult)
def update_seed(qid: int, body: GraphSeedUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, GRAPH_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.assert_not_running(db, GRAPH_ADAPTER, q)
    return qa.rebuild_seed(db, GRAPH_ADAPTER, q, {"seed_cypher": body.seed_cypher})


@router.post("/{qid}/finalize", response_model=GraphQuestionResponse)
def finalize(qid: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    q = qa.load_question(db, GRAPH_ADAPTER, qid)
    ensure_owner_or_staff(current_user, q.created_by)
    qa.finalize(db, GRAPH_ADAPTER, q)
    return _to_response(q, qa.list_tasks(db, GRAPH_ADAPTER, qid))


# ---------------------------------------------------------------------------
# Standalone "practice" solving (any authenticated user, outside any lab).
# Same grading as the in-lab path, but keyed to a per-(question, user) writable DB.
# ---------------------------------------------------------------------------

@router.post("/{qid}/run", response_model=SqlLabRunResult)
def run_graph_practice(qid: int, body: SqlLabRunRequest, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    try:
        db_path = ensure_graph_practice_session(q.id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SqlLabRunResult.from_executor(execute_graph_query(db_path, body.query, timeout=15))


@router.post("/{qid}/submit", response_model=ItemGradeResponse)
def submit_graph_practice(qid: int, body: GraphPracticeSubmit, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    task = db.query(GraphTask).filter(
        GraphTask.id == body.task_id, GraphTask.graph_question_id == q.id, GraphTask.is_deleted == 0
    ).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.correct_answer_hash:
        return ItemGradeResponse(is_passed=False, message="Task has no assigned answer")
    try:
        db_path = ensure_graph_practice_session(q.id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = execute_graph_query(db_path, body.query, timeout=15)
    if not result["success"]:
        return ItemGradeResponse(is_passed=False, message=result["error_message"] or "Query failed")
    passed = hash_run_result(result) == task.correct_answer_hash
    return ItemGradeResponse(is_passed=passed, message="Correct" if passed else "Incorrect result")


@router.get("/{qid}/database", response_model=DatabaseStateResponse)
def graph_practice_database(qid: int, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    try:
        db_path = ensure_graph_practice_session(q.id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return DatabaseStateResponse(**get_graph_schema_info(db_path))


@router.post("/{qid}/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_graph_practice_db(qid: int, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    q = _load_or_404(db, qid)
    try:
        reset_graph_practice(q.id, current_user.id)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return None
