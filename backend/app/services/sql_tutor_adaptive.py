"""Adaptive SQL-tutor orchestration (Phase 5).

Ties the mastery model, scaffolding engine, and SOLO classifier together into the
system prompt the chatbot streams. Deliberately a plain helper over the existing
``chatbot.py`` streaming path — NOT a LangGraph engine — since the flow is a couple
of DB lookups plus prompt assembly.

Entry point: ``prepare_turn(db, user_id, question)`` returns everything the /send
handler needs — the built system prompt, the SqlTutorConversation carrying
scaffolding state, and the active concept id (for telemetry).
"""
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.concept_mastery import ConceptMastery  # noqa: F401 (registration)
from app.models.question_concept import QuestionConcept
from app.models.solo_classification import SoloClassification
from app.models.sql_tutor_conversation import SqlTutorConversation
from app.services import scaffolding_engine
from app.services import sql_tutor_prompts
from app.services.learning_telemetry import log_event, EVENT_SCAFFOLDING_CHANGED

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveTurn:
    system_prompt: str
    conversation: SqlTutorConversation
    active_concept_id: Optional[int]
    scaffolding_level: str
    solo_level: Optional[str]
    used_generic_solo: bool


def resolve_active_concept(db: Session, question_id: int) -> Optional[int]:
    """The concept a question most exercises = its highest-weight tag.

    Returns None for untagged questions (scaffolding then stays at its default).
    """
    row = (
        db.query(QuestionConcept.concept_id)
        .filter(QuestionConcept.question_id == question_id)
        .order_by(QuestionConcept.weight.desc())
        .first()
    )
    return row[0] if row else None


def get_or_create_conversation(
    db: Session, user_id: int, question_id: int
) -> SqlTutorConversation:
    conv = (
        db.query(SqlTutorConversation)
        .filter(
            SqlTutorConversation.user_id == user_id,
            SqlTutorConversation.question_id == question_id,
            SqlTutorConversation.context_type == "question",
        )
        .first()
    )
    if conv is None:
        conv = SqlTutorConversation(
            user_id=user_id, question_id=question_id,
            context_type="question", scaffolding_level=scaffolding_engine.DEFAULT_LEVEL,
        )
        db.add(conv)
        db.commit()
    return conv


def latest_solo(db: Session, conversation_id: int):
    """Most recent SOLO classification for the conversation (from a prior turn)."""
    return (
        db.query(SoloClassification)
        .filter(SoloClassification.conversation_id == conversation_id)
        # Tie-break on id so same-second timestamps still yield the newest row.
        .order_by(SoloClassification.created_at.desc(), SoloClassification.id.desc())
        .first()
    )


def prepare_turn(db: Session, user_id: int, question, student_query: str = "None yet") -> AdaptiveTurn:
    """Compute scaffolding + SOLO state and build the adaptive system prompt.

    Persists any scaffolding-level transition and logs a scaffolding_changed event.
    """
    conv = get_or_create_conversation(db, user_id, question.id)

    active_concept_id = resolve_active_concept(db, question.id)
    if active_concept_id != conv.active_concept_id:
        conv.active_concept_id = active_concept_id

    # Recompute the scaffolding level from live mastery streaks for the active concept.
    new_level, changed = scaffolding_engine.evaluate_for_concept(
        db, user_id, active_concept_id, conv.scaffolding_level
    )
    if changed:
        prev = conv.scaffolding_level
        conv.scaffolding_level = new_level
        db.commit()
        log_event(
            user_id=user_id,
            event_type=EVENT_SCAFFOLDING_CHANGED,
            question_id=question.id,
            concept_id=active_concept_id,
            conversation_id=conv.id,
            payload={"from_level": prev, "to_level": new_level},
        )
    else:
        db.commit()

    # SOLO from the previous turn drives this turn's tailoring, gated by confidence.
    solo = latest_solo(db, conv.id)
    if solo is not None:
        solo_level = solo.solo_level
        used_generic = bool(solo.used_fallback) or solo.confidence < settings.SOLO_CONFIDENCE_THRESHOLD
    else:
        solo_level = None
        used_generic = True

    system_prompt = sql_tutor_prompts.build_system_prompt(
        description=getattr(question, "description", ""),
        schema_sql=getattr(question, "schema_sql", ""),
        sample_data_sql=getattr(question, "sample_data_sql", ""),
        student_query=student_query,
        scaffolding_level=conv.scaffolding_level,
        solo_level=solo_level,
        use_generic=used_generic,
    )

    return AdaptiveTurn(
        system_prompt=system_prompt,
        conversation=conv,
        active_concept_id=active_concept_id,
        scaffolding_level=conv.scaffolding_level,
        solo_level=solo_level,
        used_generic_solo=used_generic,
    )
