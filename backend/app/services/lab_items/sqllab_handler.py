from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.lab_task import LabTask
from app.core.lab_query_executor import execute_lab_query
from app.core.answer_validator import generate_hash
from app.services.lab_items.base import LabItemHandler, ItemView, GradeResult


class SqlLabSectionHandler(LabItemHandler):
    """The lab's one shared-DB section. ref_id is null; grading targets a LabTask on the session DB copy."""
    kind = "sqllab"

    def resolve(self, db: Session, ref_id: Optional[int]) -> None:
        return None  # the section is the lab itself (schema_sql + LabTasks)

    def to_view(self, db: Session, ref_id: Optional[int]) -> ItemView:
        return ItemView(kind="sqllab", ref_id=None, title="Shared-DB section")

    def grade(self, db: Session, ref_id: Optional[int], payload: dict, session: Any) -> GradeResult:
        if session is None or getattr(session, "db_file_path", None) is None:
            return GradeResult(is_passed=False, message="No active session database for this section")
        task_id = payload.get("lab_task_id")
        if task_id is None:
            return GradeResult(is_passed=False, message="No task specified")
        task = db.query(LabTask).filter(
            LabTask.id == task_id, LabTask.is_deleted == 0
        ).first()
        if not task or not task.correct_answer_hash:
            return GradeResult(is_passed=False, message="Task has no assigned answer")
        result = execute_lab_query(session.db_file_path, payload["query"], timeout=15)
        if not result["success"]:
            return GradeResult(is_passed=False, message=result["error_message"] or "Query failed")
        # execute_lab_query returns results as list of dicts; convert to tuples for generate_hash
        # (mirrors the pattern in labs.py validate_task_answer / submit_task_answer)
        results_tuples = [
            tuple(row[col] for col in result["columns"])
            for row in result["results"]
        ]
        submitted_hash = generate_hash(results_tuples, result["columns"])
        passed = submitted_hash == task.correct_answer_hash
        return GradeResult(
            is_passed=passed,
            detail={"query": payload["query"], "lab_task_id": task.id},
            message="Correct" if passed else "Incorrect result",
        )
