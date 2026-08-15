"""Learning Analytics Dashboard service (Phase 7).

Read-only aggregation over the mastery/scaffolding data the agents produce:
  - concept_graph:  the student's own concept DAG (nodes styled by mastery).
  - peer_benchmark:  anonymized class-average mastery per concept, refreshed once a
                     day via a date-stamped cache key (no write-triggered
                     invalidation), with a minimum-cohort floor.
  - scaffolding_for_question: the current support level, for the chat indicator.
"""
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core import cache
from app.models.concept_mastery import ConceptMastery
from app.models.sql_concept import SqlConcept
from app.models.sql_concept_prerequisite import SqlConceptPrerequisite
from app.models.sql_tutor_conversation import SqlTutorConversation
from app.models.user import User, UserRole
from app.services import scaffolding_engine


def mastery_band(level: Optional[float]) -> str:
    """Coarse display band derived from the smooth 0..1 mastery level."""
    if level is None:
        return "untouched"
    if level < 0.25:
        return "novice"
    if level < 0.5:
        return "developing"
    if level < 0.8:
        return "proficient"
    return "mastered"


def concept_graph(db: Session, user_id: int) -> dict:
    """Nodes (concepts + this student's mastery) and prerequisite edges."""
    concepts = (
        db.query(SqlConcept)
        .filter(SqlConcept.is_active == 1)
        .order_by(SqlConcept.category, SqlConcept.display_name)
        .all()
    )
    mastery_by_concept = {
        m.concept_id: m.mastery_level
        for m in db.query(ConceptMastery).filter(ConceptMastery.user_id == user_id).all()
    }
    nodes = []
    for c in concepts:
        level = mastery_by_concept.get(c.id)
        nodes.append({
            "id": c.id,
            "slug": c.slug,
            "display_name": c.display_name,
            "category": c.category,
            "mastery_level": round(level, 4) if level is not None else None,
            "mastery_band": mastery_band(level),
        })
    edges = [
        {"from": e.prerequisite_concept_id, "to": e.concept_id}
        for e in db.query(SqlConceptPrerequisite).all()
    ]
    return {"nodes": nodes, "edges": edges}


def _compute_peer_benchmark(db: Session, class_group: Optional[str]) -> dict:
    """Class-average mastery per concept for one class_group. Suppressed below the
    minimum-cohort floor to prevent de-anonymization."""
    if not class_group:
        return {"suppressed": True, "reason": "no_class_group", "averages": [], "cohort_size": 0}

    cohort_size = (
        db.query(func.count(User.id))
        .filter(User.class_group == class_group, User.role == UserRole.STUDENT)
        .scalar()
    ) or 0
    if cohort_size < settings.PEER_BENCHMARK_MIN_COHORT:
        return {"suppressed": True, "reason": "cohort_too_small", "averages": [], "cohort_size": cohort_size}

    rows = (
        db.query(
            ConceptMastery.concept_id,
            func.avg(ConceptMastery.mastery_level),
        )
        .join(User, User.id == ConceptMastery.user_id)
        .filter(User.class_group == class_group, User.role == UserRole.STUDENT)
        .group_by(ConceptMastery.concept_id)
        .all()
    )
    averages = [
        {"concept_id": cid, "avg_mastery": round(float(avg), 4)}
        for cid, avg in rows
    ]
    return {"suppressed": False, "reason": None, "averages": averages, "cohort_size": cohort_size}


def peer_benchmark(db: Session, class_group: Optional[str]) -> dict:
    """Peer benchmark for a class_group, cached once per calendar day.

    The date in the cache key gives daily rollover; the namespace has no
    invalidation hook, so a student's mastery write during the day does not force a
    recompute — the aggregate refreshes tomorrow.
    """
    key = (class_group or "", date.today().isoformat())
    return cache.cache_read(
        db,
        cache.Ns.CONCEPT_MASTERY_AGGREGATE,
        key,
        lambda: _compute_peer_benchmark(db, class_group),
    )


def scaffolding_for_question(db: Session, user_id: int, question_id: int) -> dict:
    """Current scaffolding level for the chat indicator. Never creates a row."""
    conv = (
        db.query(SqlTutorConversation)
        .filter(
            SqlTutorConversation.user_id == user_id,
            SqlTutorConversation.question_id == question_id,
            SqlTutorConversation.context_type == "question",
        )
        .first()
    )
    level = conv.scaffolding_level if conv else scaffolding_engine.DEFAULT_LEVEL
    return {
        "question_id": question_id,
        "scaffolding_level": level,
        "levels": scaffolding_engine.LEVELS,
    }
