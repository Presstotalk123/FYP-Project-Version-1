from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.graph_question import GraphQuestion, GraphTask
from app.core.graph_query_executor import execute_graph_query
from app.core.answer_validator import hash_run_result
from app.utils.graph_db_manager import ensure_graph_session
from app.utils.lab_db_manager import LabDatabaseError
from app.services.lab_items.base import LabItemHandler, ItemView, GradeResult


class GraphItemHandler(LabItemHandler):
    """A graph pool question: a seed graph + ordered tasks, solved on a per-(session,item) writable copy."""
    kind = "graph"

    def resolve(self, db: Session, ref_id: Optional[int]) -> GraphQuestion:
        q = db.query(GraphQuestion).filter(
            GraphQuestion.id == ref_id, GraphQuestion.is_deleted == 0
        ).first()
        if not q:
            raise ValueError("Graph question not found")
        return q

    def to_view(self, db: Session, ref_id: Optional[int]) -> ItemView:
        q = self.resolve(db, ref_id)
        return ItemView(kind="graph", ref_id=q.id, title=q.title, difficulty=q.difficulty.value)

    def grade(self, db: Session, ref_id: Optional[int], payload: dict, session: Any) -> GradeResult:
        q = self.resolve(db, ref_id)
        item_id = payload.get("lab_item_id")
        task_id = payload.get("lab_task_id")
        if session is None or item_id is None:
            return GradeResult(is_passed=False, message="No active session for this item")
        if task_id is None:
            return GradeResult(is_passed=False, message="No task specified")
        task = db.query(GraphTask).filter(
            GraphTask.id == task_id, GraphTask.graph_question_id == q.id, GraphTask.is_deleted == 0
        ).first()
        if not task or not task.correct_answer_hash:
            return GradeResult(is_passed=False, message="Task has no assigned answer")
        try:
            db_path = ensure_graph_session(q.id, session.id, item_id)
        except LabDatabaseError as e:
            return GradeResult(is_passed=False, message=str(e))
        result = execute_graph_query(db_path, payload["query"], timeout=15)
        if not result["success"]:
            return GradeResult(is_passed=False, message=result["error_message"] or "Query failed")
        passed = hash_run_result(result) == task.correct_answer_hash
        return GradeResult(
            is_passed=passed,
            detail={"query": payload["query"], "lab_task_id": task.id},
            message="Correct" if passed else "Incorrect result",
        )
