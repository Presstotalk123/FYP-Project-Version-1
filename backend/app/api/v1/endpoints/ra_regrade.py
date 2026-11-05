"""Regrade a question's past attempts with the current grader (FYP). Mounted under /ra.

  POST /ra/analytics/questions/{id}/regrade/preview   the next batch of attempts that would
                                                      change: {after_id} → {changes, checked,
                                                      total, after_id, done}
  POST /ra/analytics/questions/{id}/regrade/apply     regrade and save these attempts:
                                                      {attempt_ids} → {changed}

Staff-only; 404 while RA_ENABLED is off. Nothing changes until ``apply``, and marks given
by hand are kept (services/ra/regrade.py).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_staff_role
from app.models.ra_question import RAQuestion
from app.models.user import User
from app.services.ra import regrade

router = APIRouter(prefix="/analytics")


class RegradePreviewIn(BaseModel):
    after_id: Optional[int] = None


class RegradeApplyIn(BaseModel):
    attempt_ids: List[int] = Field(default_factory=list, max_length=regrade.MAX_APPLY)


def _question(db: Session, question_id: int) -> RAQuestion:
    q = db.query(RAQuestion).filter(RAQuestion.id == question_id, RAQuestion.is_deleted == 0).first()
    if q is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return q


@router.post("/questions/{question_id}/regrade/preview")
def regrade_preview(question_id: int, body: RegradePreviewIn, db: Session = Depends(get_db),
                    _staff: User = Depends(require_staff_role)):
    return regrade.preview(db, _question(db, question_id), body.after_id)


@router.post("/questions/{question_id}/regrade/apply")
def regrade_apply(question_id: int, body: RegradeApplyIn, db: Session = Depends(get_db),
                  _staff: User = Depends(require_staff_role)):
    return {"changed": regrade.apply(db, _question(db, question_id), body.attempt_ids)}
