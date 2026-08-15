"""SOLO Classifier Agent (Phase 6).

Background, LLM-bound agent that labels a student chat message with a SOLO
Taxonomy level and the model's self-reported confidence. When confidence falls
below ``SOLO_CONFIDENCE_THRESHOLD`` the classification is marked ``used_fallback``
so the next chatbot turn uses a generic (non-SOLO-tailored) prompt — the
confidence-gating safeguard from the spec.

Runs as a fire-and-forget background task with its own session, gated by
``AKELA_AGENTS_ENABLED``. Uses the synchronous provider SDKs (this runs in the
threadpool, not the event loop). Any failure is logged and swallowed.
"""
import json
import logging
from typing import Optional

from app.config import settings
from app.database import SessionLocal
from app.models.solo_classification import SoloClassification
from app.services.learning_telemetry import log_event, EVENT_SOLO_CLASSIFIED

logger = logging.getLogger(__name__)

SOLO_LEVELS = [
    "prestructural", "unistructural", "multistructural",
    "relational", "extended_abstract",
]

SOLO_SYSTEM_PROMPT = """You are an educational assessor applying the SOLO Taxonomy
(Structure of Observed Learning Outcomes) to a single student message from a SQL
tutoring chat. Classify the cognitive complexity of the student's message into
exactly one level:

- prestructural: no relevant understanding; off-topic or confused.
- unistructural: grasps one relevant aspect only.
- multistructural: several relevant aspects, but treated separately/unconnected.
- relational: integrates aspects into a coherent whole; explains relationships.
- extended_abstract: generalizes beyond the problem; abstracts or transfers ideas.

Respond with ONLY a JSON object, no prose, of the form:
{"solo_level": "<one of the five levels>", "confidence": <0.0-1.0>, "rationale": "<one short sentence>"}

confidence is YOUR certainty in the classification. If the message is too short or
ambiguous to classify (e.g. "ok", "thanks", "help"), return low confidence."""


def _call_provider_sync(system_prompt: str, user_message: str) -> str:
    provider = settings.AI_PROVIDER.lower()
    if provider in ("azure_openai", "openai"):
        from openai import AzureOpenAI, OpenAI
        if provider == "azure_openai":
            client = AzureOpenAI(
                api_key=settings.AI_API_KEY,
                azure_endpoint=settings.AI_AZURE_ENDPOINT,
                api_version=settings.AI_AZURE_API_VERSION,
            )
        else:
            client = OpenAI(api_key=settings.AI_API_KEY)
        kwargs = {
            "model": settings.AI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "timeout": 30,
        }
        if settings.AI_ENABLE_TEMPERATURE:
            kwargs["temperature"] = 0.0 if settings.AI_TEMPERATURE is None else settings.AI_TEMPERATURE
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
    elif provider == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=settings.AI_API_KEY)
        model = genai.GenerativeModel(
            model_name=settings.AI_MODEL, system_instruction=system_prompt,
        )
        response = model.generate_content(user_message)
        return response.text or ""
    raise ValueError(f"Unsupported AI_PROVIDER: {provider}")


def _parse(raw: str) -> Optional[dict]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```", 2)[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.rsplit("```", 1)[0].strip()
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None  # valid JSON but not an object (bare value / array)
    level = str(data.get("solo_level", "")).strip().lower()
    if level not in SOLO_LEVELS:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    return {"solo_level": level, "confidence": max(0.0, min(1.0, confidence)), "raw": raw}


def classify_message(
    user_id: int,
    conversation_id: Optional[int],
    message_id: Optional[int],
    message_text: str,
) -> None:
    """Background-task entrypoint. Classify one message and persist the result.

    No-op when AKELA_AGENTS_ENABLED is False. Best-effort; never raises.
    """
    if not settings.AKELA_AGENTS_ENABLED:
        return
    if not message_text or len(message_text.strip()) < 3:
        return  # skip trivial acks

    db = SessionLocal()
    try:
        raw = _call_provider_sync(SOLO_SYSTEM_PROMPT, message_text.strip())
        parsed = _parse(raw)
        if parsed is None:
            logger.warning("solo_classifier: unparseable output for conv=%s", conversation_id)
            return
        used_fallback = 1 if parsed["confidence"] < settings.SOLO_CONFIDENCE_THRESHOLD else 0
        row = SoloClassification(
            user_id=user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            solo_level=parsed["solo_level"],
            confidence=parsed["confidence"],
            used_fallback=used_fallback,
            raw_model_output_json=parsed["raw"],
        )
        db.add(row)
        db.commit()
        log_event(
            user_id=user_id,
            event_type=EVENT_SOLO_CLASSIFIED,
            conversation_id=conversation_id,
            payload={
                "solo_level": parsed["solo_level"],
                "confidence": parsed["confidence"],
                "used_fallback": used_fallback,
            },
        )
    except Exception:
        db.rollback()
        logger.exception("solo_classifier.classify_message failed (conv=%s)", conversation_id)
    finally:
        db.close()
