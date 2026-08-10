"""Staff-only analytics over SQL-question attempts. Shares the /questions URL prefix
with the main questions router; kept in its own module (mirrors er_analytics.py)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import Ns, cache_read
from app.database import get_db
from app.dependencies import require_staff_role
from app.models.user import User
from app.services.sql_analytics import question_analytics, student_detail

router = APIRouter(prefix="/questions", tags=["sql-analytics"])


@router.get("/{question_id}/analytics")
def get_question_analytics(
    question_id: int,
    class_group: Optional[str] = None,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    # Version-stamped cache: auto-invalidated whenever an attempt, progress row,
    # query review, tutor-chat message or user changes.
    out = cache_read(
        db,
        Ns.SQL_ANALYTICS,
        key=("question", question_id, class_group or ""),
        producer=lambda: question_analytics(db, question_id, class_group),
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Question not found")
    return out


@router.get("/{question_id}/students/{student_id}/detail")
def get_student_detail(
    question_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    return student_detail(db, question_id, student_id)
