"""Staff analytics for relational algebra (FYP). Mounted under /ra by endpoints/ra.py.

  GET /ra/analytics/class                              every practice question and student
  GET /ra/analytics/class-groups                       the class filter's options
  GET /ra/analytics/questions/{id}                     one question, per part and per student
  GET /ra/analytics/questions/{id}/students/{sid}      one student's attempts at it

All take ``class_group`` where it applies; all are staff-only and 404 while RA_ENABLED is off.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_staff_role
from app.models.user import User
from app.services.ra import analytics

router = APIRouter(prefix="/analytics")


@router.get("/class")
def get_class_analytics(class_group: Optional[str] = None, db: Session = Depends(get_db),
                        _staff: User = Depends(require_staff_role)):
    return analytics.class_analytics(db, class_group or None)


@router.get("/class-groups")
def get_class_groups(db: Session = Depends(get_db), _staff: User = Depends(require_staff_role)):
    return analytics.class_groups(db)


@router.get("/questions/{question_id}")
def get_question_analytics(question_id: int, class_group: Optional[str] = None, db: Session = Depends(get_db),
                           _staff: User = Depends(require_staff_role)):
    out = analytics.question_analytics(db, question_id, class_group or None)
    if out is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return out


@router.get("/questions/{question_id}/students/{student_id}")
def get_student_attempts(question_id: int, student_id: int, db: Session = Depends(get_db),
                         _staff: User = Depends(require_staff_role)):
    return analytics.student_attempts(db, question_id, student_id)
