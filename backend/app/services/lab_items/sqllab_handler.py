from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.sql_lab_question import SqlLabQuestion, SqlLabTask
from app.core.lab_query_executor import execute_lab_query
from app.core.answer_validator import generate_hash
from app.utils.sqllab_db_manager import ensure_sqllab_session
from app.utils.lab_db_manager import LabDatabaseError
from app.services.lab_items.base import LabItemHandler, ItemView, GradeResult


class SqlLabSectionHandler(LabItemHandler):
    """A SQL-lab pool question: a seed DB + ordered tasks, solved on a per-(session,item) writable copy."""
    kind = "sqllab"

    def resolve(self, db: Session, ref_id: Optional[int]) -> SqlLabQuestion:
        q = db.query(SqlLabQuestion).filter(
            SqlLabQuestion.id == ref_id, SqlLabQuestion.is_deleted == 0
        ).first()
        if not q:
            raise ValueError("SQL-lab question not found")
        return q

    def to_view(self, db: Session, ref_id: Optional[int]) -> ItemView:
        q = self.resolve(db, ref_id)
        return ItemView(kind="sqllab", ref_id=q.id, title=q.title, difficulty=q.difficulty.value)

    def grade(self, db: Session, ref_id: Optional[int], payload: dict, session: Any) -> GradeResult:
        q = self.resolve(db, ref_id)
        item_id = payload.get("lab_item_id")
        task_id = payload.get("lab_task_id")
        if session is None or item_id is None:
            return GradeResult(is_passed=False, message="No active session for this item")
        if task_id is None:
            return GradeResult(is_passed=False, message="No task specified")
        task = db.query(SqlLabTask).filter(
            SqlLabTask.id == task_id, SqlLabTask.sql_lab_question_id == q.id, SqlLabTask.is_deleted == 0
        ).first()
        if not task or not task.correct_answer_hash:
            return GradeResult(is_passed=False, message="Task has no assigned answer")
        try:
            db_path = ensure_sqllab_session(q.id, session.id, item_id)
        except LabDatabaseError as e:
            return GradeResult(is_passed=False, message=str(e))
        result = execute_lab_query(db_path, payload["query"], timeout=15)
        if not result["success"]:
            return GradeResult(is_passed=False, message=result["error_message"] or "Query failed")
        results_tuples = [tuple(row[col] for col in result["columns"]) for row in result["results"]]
        passed = generate_hash(results_tuples, result["columns"]) == task.correct_answer_hash
        return GradeResult(
            is_passed=passed,
            detail={"query": payload["query"], "lab_task_id": task.id},
            message="Correct" if passed else "Incorrect result",
        )
