"""Shared two-phase authoring core for the SQL-lab and Graph pool question types.

Both types are structurally identical (a seed DB + ordered tasks with a hashed
answer). This module holds the logic once; per-type differences are captured in
an AuthoringAdapter. The endpoint files are thin wrappers that pass the right
adapter and translate request/response shapes.
"""
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.answer_validator import hash_run_result
from app.core.lab_query_executor import execute_lab_query
from app.core.graph_query_executor import execute_graph_query
from app.models.sql_lab_question import SqlLabQuestion, SqlLabTask
from app.models.graph_question import GraphQuestion, GraphTask
from app.services.lab_refs import running_labs_referencing
from app.utils.lab_db_manager import LabDatabaseError
from app.utils import sqllab_db_manager as sqlm
from app.utils import graph_db_manager as graphm
from app.schemas.lab import SeedRebuildResult


@dataclass(frozen=True)
class AuthoringAdapter:
    kind: str
    question_model: type
    task_model: type
    task_fk: str
    seed_fields: tuple[str, ...]
    build_template: Callable[[int, dict], None]      # (question_id, seed_dict) -> builds template, raises LabDatabaseError
    template_path: Callable[[int], str]
    execute: Callable[[str, str], dict]              # (template_path, query) -> executor result dict
    reset_practice: Callable[[int, int], None]       # (question_id, user_id)


def _sqllab_build(qid: int, seed: dict) -> None:
    sqlm.create_sqllab_template(qid, seed["schema_sql"], seed["sample_data_sql"])


def _graph_build(qid: int, seed: dict) -> None:
    # create_graph_template(id, schema_cypher, seed_cypher): graph carries everything in one field.
    graphm.create_graph_template(qid, seed["seed_cypher"], "")


SQLLAB_ADAPTER = AuthoringAdapter(
    kind="sqllab",
    question_model=SqlLabQuestion,
    task_model=SqlLabTask,
    task_fk="sql_lab_question_id",
    seed_fields=("schema_sql", "sample_data_sql"),
    build_template=_sqllab_build,
    template_path=sqlm.get_sqllab_template_path,
    execute=lambda path, q: execute_lab_query(path, q, timeout=15),
    reset_practice=sqlm.reset_sqllab_practice,
)

GRAPH_ADAPTER = AuthoringAdapter(
    kind="graph",
    question_model=GraphQuestion,
    task_model=GraphTask,
    task_fk="graph_question_id",
    seed_fields=("seed_cypher",),
    build_template=_graph_build,
    template_path=graphm.get_graph_template_path,
    execute=lambda path, q: execute_graph_query(path, q, timeout=15),
    reset_practice=graphm.reset_graph_practice,
)


def load_question(db: Session, adapter: AuthoringAdapter, qid: int):
    q = (db.query(adapter.question_model)
         .filter(adapter.question_model.id == qid, adapter.question_model.is_deleted == 0)
         .first())
    if not q:
        raise HTTPException(status_code=404, detail=f"{adapter.kind} question not found")
    return q


def list_tasks(db: Session, adapter: AuthoringAdapter, qid: int) -> list:
    fk = getattr(adapter.task_model, adapter.task_fk)
    return (db.query(adapter.task_model)
            .filter(fk == qid, adapter.task_model.is_deleted == 0)
            .order_by(adapter.task_model.order_index)
            .all())


def create_draft(db: Session, adapter: AuthoringAdapter, *, title: str, description: str,
                 difficulty: Any, seed: dict, created_by: int):
    q = adapter.question_model(
        title=title, description=description, difficulty=difficulty,
        created_by=created_by, is_deleted=0, status="draft",
        **{f: seed[f] for f in adapter.seed_fields},
    )
    db.add(q)
    db.flush()  # get q.id
    try:
        adapter.build_template(q.id, seed)
        q.template_db_path = f"{adapter.kind}_q_{q.id}_template.db"
    except LabDatabaseError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Failed to build question database: {str(e)}")
    db.commit()
    db.refresh(q)
    return q


def add_task(db: Session, adapter: AuthoringAdapter, q, *, title: str, description: str):
    existing = list_tasks(db, adapter, q.id)
    next_index = (existing[-1].order_index + 1) if existing else 0
    task = adapter.task_model(title=title, description=description,
                              order_index=next_index, is_deleted=0,
                              **{adapter.task_fk: q.id})
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def assign_answer(db: Session, adapter: AuthoringAdapter, q, task, *, query: str):
    result = adapter.execute(adapter.template_path(q.id), query)
    if not result["success"]:
        raise HTTPException(status_code=400,
                            detail=f"Correct query failed: {result['error_message']}")
    task.correct_query = query
    task.correct_answer_hash = hash_run_result(result)
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, task, *, title=None, description=None):
    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    db.commit()
    db.refresh(task)
    return task


def soft_delete_task(db: Session, task) -> None:
    task.is_deleted = 1
    db.commit()


def reorder_tasks(db: Session, adapter: AuthoringAdapter, q, ordered_ids: list[int]) -> list:
    tasks = {t.id: t for t in list_tasks(db, adapter, q.id)}
    if set(ordered_ids) != set(tasks.keys()):
        raise HTTPException(status_code=400, detail="ordered_ids must list every current task exactly once")
    for index, tid in enumerate(ordered_ids):
        tasks[tid].order_index = index
    db.commit()
    return list_tasks(db, adapter, q.id)


def finalize(db: Session, adapter: AuthoringAdapter, q):
    tasks = list_tasks(db, adapter, q.id)
    if not tasks:
        raise HTTPException(status_code=400, detail="Add at least one task before finalizing")
    unanswered = [t.title for t in tasks if t.correct_answer_hash is None]
    if unanswered:
        raise HTTPException(status_code=400,
                            detail=f"These tasks need an assigned answer: {', '.join(unanswered)}")
    q.status = "ready"
    db.commit()
    db.refresh(q)
    return q


def rebuild_seed(db: Session, adapter: AuthoringAdapter, q, seed: dict) -> SeedRebuildResult:
    # Overwrite the template DB with the new seed.
    for f in adapter.seed_fields:
        setattr(q, f, seed[f])
    try:
        adapter.build_template(q.id, seed)
    except LabDatabaseError as e:
        raise HTTPException(status_code=400, detail=f"Failed to rebuild database: {str(e)}")

    # Re-run every task's correct query against the fresh template; update or clear its hash.
    warnings: list[str] = []
    for task in list_tasks(db, adapter, q.id):
        if not task.correct_query:
            continue
        result = adapter.execute(adapter.template_path(q.id), task.correct_query)
        if result["success"]:
            task.correct_answer_hash = hash_run_result(result)
        else:
            task.correct_answer_hash = None
            warnings.append(f"Task '{task.title}' lost its answer (query no longer runs) — re-assign it.")

    # Invariant: ready ⇒ every task answered. If a hash was cleared, drop back to draft.
    if any(t.correct_answer_hash is None for t in list_tasks(db, adapter, q.id)):
        if q.status == "ready":
            warnings.append("Question returned to draft until all tasks are answered again.")
        q.status = "draft"

    # The author's practice copy was made from the old template — discard it.
    try:
        adapter.reset_practice(q.id, q.created_by)
    except LabDatabaseError:
        pass

    db.commit()
    db.refresh(q)
    return SeedRebuildResult(status=q.status, warnings=warnings)


def assert_not_running(db: Session, adapter: AuthoringAdapter, q) -> None:
    running = running_labs_referencing(db, adapter.kind, q.id)
    if running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stop these running labs before editing: {', '.join(running)}",
        )
