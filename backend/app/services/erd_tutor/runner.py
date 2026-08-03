"""Public SSE entrypoints for the ERD tutor engine (Tasks 5.4 + 6.3).

``stream_er_submission_grading`` is a drop-in for the existing Dify submit
streamer: it emits the same SSE events and a ``done`` payload whose
``structured_output`` is a ``SubmitResult`` dict so ``er_lab_submission_persistence``
keeps working unchanged.

``stream_er_query`` streams the query (tutor) path token-by-token: it streams
the tutor LLM's answer directly (SSE ``token`` events) and then derives the IBL
``state_update`` from the completed answer. It deliberately does *not* run the
compiled query graph, because a graph ``ainvoke`` only yields the final text.

NOTE: ``build_submit_graph`` and the tutor building blocks (``_tutor_messages``,
``state_update_node``, ``make_llm``) are imported at *module scope* so tests can
monkeypatch them by attribute (``monkeypatch.setattr(runner, "build_submit_graph"/
"make_llm", ...)``).
"""

import base64, json, logging
from typing import AsyncIterator, Optional
from app.services.erd_tutor.submit_graph import build_submit_graph
from app.services.erd_tutor.nodes import _tutor_messages, state_update_node
from app.services.erd_tutor.llm import make_llm

logger = logging.getLogger(__name__)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chunk_text(chunk) -> str:
    """Extract the text delta from a streamed ``AIMessageChunk``. ``content`` is a
    plain ``str`` for text models but can be a list of content parts for
    multimodal ones — join the text parts and ignore non-text blocks."""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            (part.get("text", "") or "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content or "")


def _image_b64(image_bytes: Optional[bytes]) -> Optional[str]:
    if not image_bytes: return None
    mime = "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff": mime = "image/jpeg"
    elif image_bytes[:6] in (b"GIF87a", b"GIF89a"): mime = "image/gif"
    elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP": mime = "image/webp"
    return f"data:{mime};base64," + base64.b64encode(image_bytes).decode()


def stream_er_submission_grading(*, question_id: int, problem_statement: str,
        difficulty_label: str, rubric_json: str, submission_xml_text: Optional[str],
        student_query: Optional[str] = None, erd_img=None, image_bytes: Optional[bytes] = None,
        ibl_stage: str = "orientation", hint_level: int = 1,
        last_submit_report: Optional[dict] = None,
        submission_description: Optional[str] = None) -> AsyncIterator[str]:
    async def gen() -> AsyncIterator[str]:
        yield _sse("start", {"mode": "Submit", "question_id": question_id})
        try:
            graph = build_submit_graph()
            out = await graph.ainvoke({
                "mode": "Submit", "problem_statement": problem_statement,
                "difficulty": difficulty_label, "rubric_json": rubric_json,
                # WIP: carried into state for a planned post-migration feature;
                # no node consumes it yet. (submission_xml_text is accepted for
                # signature compatibility but the graph has no XML path.)
                "submission_description": submission_description,
                "image_b64": _image_b64(image_bytes),
                "ibl_stage": ibl_stage, "hint_level": hint_level,
                "last_submit_report": last_submit_report or {}})
            result = out["result"]
            yield _sse("structured_output", {"structured_output": result})
            # canonical_erd rides alongside (not inside) structured_output so
            # er_lab_submission_persistence's contract is untouched; the
            # conversation-state overlay persists it for the query tutor.
            yield _sse("done", {"mode": "Submit", "text": result.get("student_message", ""),
                                "structured_output": result,
                                "canonical_erd": out.get("canonical_erd") or {}})
        except Exception as exc:  # parity with the Dify path's error event
            logger.warning("erd_tutor submit failed question_id=%s: %s", question_id, exc)
            yield _sse("error", {"detail": str(exc)})
    return gen()


def stream_er_query(*, question_id: int, problem_statement: str, difficulty_label: str,
        rubric_json: str, student_query: str, image_bytes: Optional[bytes] = None,
        ibl_stage: str = "orientation", hint_level: int = 1,
        current_erd_model: Optional[dict] = None,
        last_submit_report: Optional[dict] = None) -> AsyncIterator[str]:
    async def gen() -> AsyncIterator[str]:
        yield _sse("start", {"mode": "Query", "question_id": question_id})
        try:
            state = {
                "mode": "Query", "problem_statement": problem_statement,
                "difficulty": difficulty_label, "rubric_json": rubric_json,
                "student_query": student_query, "image_b64": _image_b64(image_bytes),
                "ibl_stage": ibl_stage, "hint_level": hint_level,
                "current_erd_model": current_erd_model or {},
                "last_submit_report": last_submit_report or {}}
            # 1) Stream the tutor's answer token-by-token. Each SSE `token` carries
            #    the incremental `chunk` plus the accumulated `text` so the client
            #    can render whichever it prefers.
            parts: list[str] = []
            async for chunk in make_llm("tutor").astream(_tutor_messages(state)):
                delta = _chunk_text(chunk)
                if delta:
                    parts.append(delta)
                    yield _sse("token", {"chunk": delta, "text": "".join(parts)})
            tutor_text = "".join(parts)
            # 2) Derive the IBL state update from the completed answer (same node
            #    the graph would have run next).
            upd = await state_update_node({**state, "tutor_text": tutor_text})
            yield _sse("done", {"mode": "Query", "text": tutor_text,
                                "structured_output": {"state_update": upd.get("state_update", {})}})
        except Exception as exc:
            logger.warning("erd_tutor query failed question_id=%s: %s", question_id, exc)
            yield _sse("error", {"detail": str(exc)})
    return gen()
