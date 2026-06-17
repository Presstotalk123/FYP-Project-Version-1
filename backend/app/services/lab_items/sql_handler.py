from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.question import Question
from app.core.query_executor import execute_student_query
from app.core.answer_validator import validate_answer
from app.utils.db_generator import get_question_db_path
from app.services.lab_items.base import LabItemHandler, ItemView, GradeResult


class SqlItemHandler(LabItemHandler):
    kind = "sql"

    def resolve(self, db: Session, ref_id: Optional[int]) -> Question:
        q = db.query(Question).filter(Question.id == ref_id, Question.is_deleted == 0).first()
        if not q:
            raise ValueError("SQL question not found")
        return q

    def to_view(self, db: Session, ref_id: Optional[int]) -> ItemView:
        q = self.resolve(db, ref_id)
        return ItemView(kind="sql", ref_id=q.id, title=q.title, difficulty=q.difficulty.value)

    def grade(self, db: Session, ref_id: Optional[int], payload: dict, session: Any) -> GradeResult:
        q = self.resolve(db, ref_id)
        result = execute_student_query(get_question_db_path(q.db_file_path), payload["query"])
        if not result["success"]:
            return GradeResult(is_passed=False, message=result["error_message"] or "Query failed")
        passed = validate_answer(result["raw_results"], result["columns"], q.correct_answer_hash)
        return GradeResult(
            is_passed=passed,
            detail={"query": payload["query"]},
            message="Correct" if passed else "Incorrect result",
        )
