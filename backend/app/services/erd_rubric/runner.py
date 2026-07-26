"""Public entrypoint for the LangGraph ERD rubric generator.

A single structured LLM call (no graph): normalize inputs (port of the Dify
code node), build system + user messages with the optional model-answer image
as a vision block, and return the {difficulty, rubric_json, rubric_md,
diff_summary} dict — the same shape the Dify path returns.

``make_rubric_llm`` is imported at module scope so tests can monkeypatch
``runner.make_rubric_llm``.
"""

import base64
import json
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage

from app.services.erd_rubric import prompts
from app.services.erd_rubric.schemas import RubricGeneration
from app.services.erd_rubric.llm import make_rubric_llm


def _normalize_previous(rubric_previous) -> str:
    """Rubric_Previous -> JSON string; '{}' when empty. Port of the Dify code node."""
    if isinstance(rubric_previous, str):
        return rubric_previous if rubric_previous.strip() else "{}"
    return json.dumps(rubric_previous or {})


def _normalize_history(instruction_history) -> str:
    """Instruction_History -> JSON array string; unwraps {'history': [...]}; '[]' when empty."""
    raw = instruction_history
    if isinstance(raw, str):
        return raw if raw.strip() else "[]"
    hist = []
    if isinstance(raw, list):
        hist = raw
    elif isinstance(raw, dict) and isinstance(raw.get("history"), list):
        hist = raw["history"]
    return json.dumps(hist or [])


def _image_b64(image_bytes: Optional[bytes]) -> Optional[str]:
    if not image_bytes:
        return None
    mime = "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        mime = "image/jpeg"
    elif image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        mime = "image/gif"
    elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        mime = "image/webp"
    return f"data:{mime};base64," + base64.b64encode(image_bytes).decode()


def generate_rubric(*, mode: str, notation: str, problem_statement: str,
                    refinement_instruction: Optional[str] = None,
                    rubric_previous=None, instruction_history=None,
                    image_bytes: Optional[bytes] = None) -> dict:
    user_text = (
        prompts.RUBRIC_USER
        .replace("[[MODE]]", mode or "")
        .replace("[[NOTATION]]", notation or "")
        .replace("[[PROBLEM_STATEMENT]]", problem_statement or "")
        .replace("[[RUBRIC_PREVIOUS_STR]]", _normalize_previous(rubric_previous))
        .replace("[[INSTRUCTION_HISTORY_STR]]", _normalize_history(instruction_history))
        .replace("[[REFINEMENT_INSTRUCTION]]", refinement_instruction or "")
    )
    content = [{"type": "text", "text": user_text}]
    b64 = _image_b64(image_bytes)
    if b64:
        content.append({"type": "image_url", "image_url": {"url": b64, "detail": "high"}})

    llm = make_rubric_llm().with_structured_output(RubricGeneration)
    result = llm.invoke([SystemMessage(prompts.RUBRIC_SYSTEM), HumanMessage(content=content)])
    return result.model_dump()
