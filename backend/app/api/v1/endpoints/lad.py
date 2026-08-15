"""Learning Analytics Dashboard (LAD) + concept-tagging endpoints.

Student-facing reads:
  GET /lad/concept-graph                 — the student's own concept DAG.
  GET /lad/peer-benchmark                — anonymized class-average mastery per concept.
  GET /lad/scaffolding/{question_id}     — current AI support level (chat indicator).

Concept taxonomy + question tagging (staff):
  GET  /lad/concepts                     — list all concepts (any authenticated user).
  GET  /lad/questions/{qid}/concepts     — a question's current tags.
  PUT  /lad/questions/{qid}/concepts     — replace a question's tags (staff only).
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.models.user import User
from app.models.question import Question
from app.models.sql_concept import SqlConcept
from app.models.question_concept import QuestionConcept
from app.services import lad_service

router = APIRouter(prefix="/lad", tags=["lad"])


# --- schemas ----------------------------------------------------------------

class ConceptOut(BaseModel):
    id: int
    slug: str
    display_name: str
    category: str


class QuestionConceptOut(BaseModel):
    concept_id: int
    weight: float


class QuestionConceptTag(BaseModel):
    concept_id: int
    weight: float = 1.0


class SetQuestionConcepts(BaseModel):
    tags: List[QuestionConceptTag]


# --- student-facing reads ---------------------------------------------------

@router.get("/concept-graph")
def get_concept_graph(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The requesting student's concept dependency graph, nodes styled by mastery."""
    return lad_service.concept_graph(db, current_user.id)


@router.get("/peer-benchmark")
def get_peer_benchmark(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Anonymized class-average mastery per concept for the student's class group."""
    return lad_service.peer_benchmark(db, current_user.class_group)


@router.get("/scaffolding/{question_id}")
def get_scaffolding(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current AI support level for this student on this question (chat indicator)."""
    return lad_service.scaffolding_for_question(db, current_user.id, question_id)


# --- concepts + tagging -----------------------------------------------------

@router.get("/concepts", response_model=List[ConceptOut])
def list_concepts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    concepts = (
        db.query(SqlConcept)
        .filter(SqlConcept.is_active == 1)
        .order_by(SqlConcept.category, SqlConcept.display_name)
        .all()
    )
    return [
        ConceptOut(id=c.id, slug=c.slug, display_name=c.display_name, category=c.category)
        for c in concepts
    ]


@router.get("/questions/{question_id}/concepts", response_model=List[QuestionConceptOut])
def get_question_concepts(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(QuestionConcept)
        .filter(QuestionConcept.question_id == question_id)
        .all()
    )
    return [QuestionConceptOut(concept_id=r.concept_id, weight=r.weight) for r in rows]


@router.put("/questions/{question_id}/concepts", response_model=List[QuestionConceptOut])
def set_question_concepts(
    question_id: int,
    body: SetQuestionConcepts,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Replace a question's concept tags (staff only). Idempotent full-set replace."""
    question = db.query(Question).filter(Question.id == question_id).first()
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    valid_ids = {
        cid for (cid,) in db.query(SqlConcept.id).filter(
            SqlConcept.id.in_([t.concept_id for t in body.tags] or [-1])
        ).all()
    }
    for t in body.tags:
        if t.concept_id not in valid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown concept_id {t.concept_id}",
            )

    db.query(QuestionConcept).filter(QuestionConcept.question_id == question_id).delete()
    # De-dupe on concept_id (last weight wins) to respect the unique constraint.
    seen = {}
    for t in body.tags:
        seen[t.concept_id] = t.weight
    for concept_id, weight in seen.items():
        db.add(QuestionConcept(question_id=question_id, concept_id=concept_id, weight=weight))
    db.commit()

    return [QuestionConceptOut(concept_id=cid, weight=w) for cid, w in seen.items()]
