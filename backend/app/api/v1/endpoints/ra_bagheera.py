"""Bagheera, the AI tutor, on RA questions (FYP). Mounted under /ra.

  GET  /ra/questions/{id}/bagheera            is it available here (and why not), and the
                                              student's conversation on this question
  POST /ra/questions/{id}/bagheera/chat       ask: {part_id, message, answer | step_answers}
  POST /ra/questions/{id}/bagheera/explain    "Explain my mistake": {attempt_id}; one per attempt

Hints only; it never grades. Off in assessments and on questions that hide correctness
(for students). Every reply passes the leak guard first (services/ra/bagheera.py).
404 while RA_ENABLED is off.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.ra_question import RAQuestion
from app.models.user import User
from app.services.ra import bagheera, questions as svc

router = APIRouter(prefix="/questions")
MAX_MESSAGE = 2000
MAX_ANSWER = 20_000


class BagheeraChatIn(BaseModel):
    part_id: Optional[int] = None
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE)
    answer: Optional[str] = Field(None, max_length=MAX_ANSWER)
    step_answers: Optional[List[str]] = Field(None, max_length=20)


class BagheeraExplainIn(BaseModel):
    attempt_id: int


def _question(db: Session, question_id: int, user: User) -> RAQuestion:
    q = db.query(RAQuestion).filter(RAQuestion.id == question_id).first()
    if q is None or not svc.visible_to(db, q, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Question not found")
    return q


@router.get("/{question_id}/bagheera")
def get_bagheera(question_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = _question(db, question_id, user)
    reason = bagheera.available(q, user)
    return {"available": reason is None, "reason": reason,
            "messages": bagheera.conversation(db, user.id, q.id) if reason is None else []}


@router.post("/{question_id}/bagheera/chat")
async def bagheera_chat(question_id: int, body: BagheeraChatIn, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)):
    q = _question(db, question_id, user)
    try:
        part = svc.part_for(db, q, body.part_id)
    except svc.PartNotFound as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    reply = await bagheera.chat(db, user, q, part, body.message.strip(), body.answer, body.step_answers)
    return bagheera.message_out(reply)


@router.post("/{question_id}/bagheera/explain")
async def bagheera_explain(question_id: int, body: BagheeraExplainIn, db: Session = Depends(get_db),
                           user: User = Depends(get_current_user)):
    q = _question(db, question_id, user)
    return bagheera.message_out(await bagheera.explain(db, user, q, body.attempt_id))
