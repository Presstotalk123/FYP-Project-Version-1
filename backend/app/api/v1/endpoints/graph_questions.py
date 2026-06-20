from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, ensure_owner_or_staff
from app.models.user import User
from app.models.graph_question import GraphQuestion, GraphTask
from app.schemas.graph_question import (
    GraphQuestionCreate, GraphQuestionResponse, GraphTaskView,
    GraphQuestionListItem, GraphPracticeSubmit,
)
from app.schemas.lab import SqlLabRunRequest, SqlLabRunResult, ItemGradeResponse, DatabaseStateResponse
from app.utils.graph_db_manager import (
    create_graph_template, get_graph_template_path, ensure_graph_practice_session,
    reset_graph_practice, get_graph_schema_info,
)
from app.utils.lab_db_manager import LabDatabaseError
from app.core.graph_query_executor import execute_graph_query
from app.core.answer_validator import hash_run_result
from app.services.lab_refs import labs_referencing

router = APIRouter(prefix="/graph-questions", tags=["graph-questions"])


def _to_response(q: GraphQuestion, tasks: list[GraphTask]) -> GraphQuestionResponse:
    return GraphQuestionResponse(
        id=q.id, title=q.title, description=q.description, difficulty=q.difficulty.value,
        seed_cypher=q.seed_cypher,
        created_by=q.created_by, created_at=q.created_at,
        tasks=[GraphTaskView(id=t.id, title=t.title, description=t.description,
                             order_index=t.order_index, has_answer=t.correct_answer_hash is not None)
               for t in tasks],
    )


@router.post("", response_model=GraphQuestionResponse, status_code=status.HTTP_201_CREATED)
def create_graph_question(
    data: GraphQuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = GraphQuestion(
        title=data.title, description=data.description, difficulty=data.difficulty,
        seed_cypher=data.seed_cypher,
        created_by=current_user.id, is_deleted=0,
    )
    db.add(q)
    db.flush()  # get q.id

    # Build the template DB from the single seed Cypher script
    try:
        create_graph_template(q.id, data.seed_cypher, "")
        q.template_db_path = f"graph_q_{q.id}_template.db"
    except LabDatabaseError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to build question database: {str(e)}")

    # Create tasks and assign each answer hash by running its correct query on the template
    template_path = get_graph_template_path(q.id)
    tasks: list[GraphTask] = []
    for idx, t in enumerate(data.tasks):
        result = execute_graph_query(template_path, t.correct_query, timeout=15)
        if not result["success"]:
            db.rollback()
            raise HTTPException(
                status_code=400,
                detail=f"Task {idx + 1} ({t.title}) correct query failed: {result['error_message']}",
            )
        task = GraphTask(
            graph_question_id=q.id, title=t.title, description=t.description, order_index=idx,
            correct_query=t.correct_query, correct_answer_hash=hash_run_result(result),
        )
        db.add(task)
        tasks.append(task)

    db.commit()
    db.refresh(q)
    for t in tasks:
        db.refresh(t)
    return _to_response(q, tasks)


@router.get("", response_model=List[GraphQuestionListItem])
def list_graph_questions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (db.query(GraphQuestion, func.count(GraphTask.id))
            .outerjoin(GraphTask, (GraphTask.graph_question_id == GraphQuestion.id)
                       & (GraphTask.is_deleted == 0))
            .filter(GraphQuestion.is_deleted == 0)
            .group_by(GraphQuestion.id)
            .order_by(GraphQuestion.created_at.desc())
            .all())
    return [GraphQuestionListItem(id=q.id, title=q.title, difficulty=q.difficulty.value,
                                  task_count=n, created_by=q.created_by, created_at=q.created_at)
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
    refs = labs_referencing(db, "graph", qid)
    if refs:
        raise HTTPException(status_code=409, detail=f"In use by lab(s): {', '.join(refs)}")
    q.is_deleted = 1
    for t in db.query(GraphTask).filter(GraphTask.graph_question_id == qid).all():
        t.is_deleted = 1
    db.commit()
    return None


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
