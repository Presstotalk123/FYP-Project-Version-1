"""Learner Profiling Agent (Phase 3).

Deterministic, no-LLM mastery updates. After a student submits a query, this
updates their ``concept_mastery`` for every concept the question is tagged with
(``question_concepts``), using streak arithmetic scaled by each tag's weight.

Runs as a fire-and-forget background task (its own session), gated by
``AKELA_AGENTS_ENABLED``. Being pure arithmetic, the core ``apply_attempt`` is
directly unit-testable with a caller-supplied session and no network.
"""
import logging
from datetime import datetime, timezone
from typing import List

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.concept_mastery import ConceptMastery
from app.models.question_concept import QuestionConcept

logger = logging.getLogger(__name__)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def apply_attempt(db: Session, user_id: int, question_id: int, is_correct: bool) -> List[int]:
    """Update ConceptMastery for every concept tagged on ``question_id``.

    Deterministic rule per tagged concept (delta scaled by the tag weight):
      correct  -> consecutive_successes += 1, consecutive_failures = 0,
                  mastery_level += SUCCESS_DELTA * weight
      incorrect-> consecutive_failures += 1, consecutive_successes = 0,
                  mastery_level -= FAILURE_DELTA * weight

    Returns the list of concept_ids that were updated. Commits the session.
    """
    tags = (
        db.query(QuestionConcept.concept_id, QuestionConcept.weight)
        .filter(QuestionConcept.question_id == question_id)
        .all()
    )
    if not tags:
        return []

    now = datetime.now(timezone.utc)
    updated: List[int] = []

    for concept_id, weight in tags:
        weight = weight if weight is not None else 1.0
        mastery = (
            db.query(ConceptMastery)
            .filter(
                ConceptMastery.user_id == user_id,
                ConceptMastery.concept_id == concept_id,
            )
            .first()
        )
        if mastery is None:
            mastery = ConceptMastery(
                user_id=user_id, concept_id=concept_id,
                mastery_level=0.0, consecutive_successes=0,
                consecutive_failures=0, total_attempts=0,
            )
            db.add(mastery)

        if is_correct:
            mastery.consecutive_successes += 1
            mastery.consecutive_failures = 0
            mastery.mastery_level = _clamp(
                mastery.mastery_level + settings.CONCEPT_MASTERY_SUCCESS_DELTA * weight
            )
        else:
            mastery.consecutive_failures += 1
            mastery.consecutive_successes = 0
            mastery.mastery_level = _clamp(
                mastery.mastery_level - settings.CONCEPT_MASTERY_FAILURE_DELTA * weight
            )
        mastery.total_attempts += 1
        mastery.last_attempt_at = now
        updated.append(concept_id)

    db.commit()
    return updated


def process_query_submitted(user_id: int, question_id: int, is_correct: bool) -> None:
    """Background-task entrypoint: open a short-lived session and update mastery.

    Best-effort; never raises. No-op when AKELA_AGENTS_ENABLED is False.
    """
    if not settings.AKELA_AGENTS_ENABLED:
        return
    db = SessionLocal()
    try:
        apply_attempt(db, user_id, question_id, is_correct)
    except Exception:
        db.rollback()
        logger.exception(
            "learner_profiling.process_query_submitted failed (user=%s question=%s)",
            user_id, question_id,
        )
    finally:
        db.close()
