from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.er_diagram_question import ERDiagramQuestion
from app.services.lab_items.base import LabItemHandler, ItemView


class ErdItemHandler(LabItemHandler):
    """ERD pool question. Grading is streamed (Dify) by the submit endpoint, not synchronous."""
    kind = "erd"

    def resolve(self, db: Session, ref_id: Optional[int]) -> ERDiagramQuestion:
        q = db.query(ERDiagramQuestion).filter(
            ERDiagramQuestion.id == ref_id, ERDiagramQuestion.is_deleted == 0
        ).first()
        if not q:
            raise ValueError("ER question not found")
        return q

    def to_view(self, db: Session, ref_id: Optional[int]) -> ItemView:
        q = self.resolve(db, ref_id)
        return ItemView(kind="erd", ref_id=q.id, title=q.title, difficulty=q.difficulty_label)
