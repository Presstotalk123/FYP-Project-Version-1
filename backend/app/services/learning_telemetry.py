"""Centralized learning-event telemetry (Phase 1).

``log_event`` appends one row to ``learning_events`` in its own short-lived
session, fully isolated from the request that triggered it, and never raises —
telemetry must never turn a student action into an error. All writes are gated by
``settings.AKELA_AGENTS_ENABLED`` so the whole subsystem is inert until flipped on.

Intended to be scheduled via FastAPI ``BackgroundTasks`` so it runs after the
response has been sent:

    background_tasks.add_task(
        log_event, user_id=user.id, event_type=EVENT_QUERY_SUBMITTED,
        question_id=qid, payload={"is_correct": is_correct},
    )
"""
import json
import logging
from typing import Optional

from app.config import settings
from app.database import SessionLocal
from app.models.learning_event import LearningEvent

logger = logging.getLogger(__name__)

# Canonical event-type slugs (keep in sync with any analytics that read them).
EVENT_QUERY_SUBMITTED = "query_submitted"
EVENT_HINT_REQUESTED = "hint_requested"
EVENT_CHAT_OPENED = "chat_opened"
EVENT_CHAT_MESSAGE = "chat_message"
EVENT_METACOGNITIVE_PROMPT_SHOWN = "metacognitive_prompt_shown"
EVENT_SCAFFOLDING_CHANGED = "scaffolding_changed"
EVENT_SOLO_CLASSIFIED = "solo_classified"


def log_event(
    *,
    user_id: int,
    event_type: str,
    question_id: Optional[int] = None,
    lab_task_id: Optional[int] = None,
    concept_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> Optional[int]:
    """Append one learning event. Best-effort; returns the new row id or None.

    No-op (returns None) when AKELA_AGENTS_ENABLED is False. Any failure is logged
    and swallowed so callers — including background tasks — never propagate it.
    """
    if not settings.AKELA_AGENTS_ENABLED:
        return None

    db = SessionLocal()
    try:
        event = LearningEvent(
            user_id=user_id,
            event_type=event_type,
            question_id=question_id,
            lab_task_id=lab_task_id,
            concept_id=concept_id,
            conversation_id=conversation_id,
            payload_json=json.dumps(payload) if payload is not None else None,
        )
        db.add(event)
        db.commit()
        return event.id
    except Exception:
        db.rollback()
        logger.exception("learning_telemetry.log_event failed (event_type=%s)", event_type)
        return None
    finally:
        db.close()
