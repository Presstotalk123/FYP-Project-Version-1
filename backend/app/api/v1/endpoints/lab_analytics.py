"""Staff-only analytics over Lab attempts/submissions. Shares the /labs URL prefix
with the main labs router; kept in its own module (mirrors er_analytics.py)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.cache import Ns, cache_read
from app.database import get_db
from app.dependencies import require_staff_role
from app.models.user import User
from app.services.lab_analytics import lab_analytics, student_detail

router = APIRouter(prefix="/labs", tags=["lab-analytics"])


@router.get("/{lab_id}/analytics")
def get_lab_analytics(
    lab_id: int,
    class_group: Optional[str] = None,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    # Version-stamped cache: auto-invalidated whenever a lab attempt/submission,
    # query review, tutor-chat message or user changes.
    out = cache_read(
        db,
        Ns.LAB_ANALYTICS,
        key=("lab", lab_id, class_group or ""),
        producer=lambda: lab_analytics(db, lab_id, class_group),
    )
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Lab not found")
    return out


@router.get("/{lab_id}/students/{student_id}/detail")
def get_student_detail(
    lab_id: int,
    student_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    return student_detail(db, lab_id, student_id)
