"""Public SSE entrypoints for the ERD tutor engine (Tasks 5.4 + 6.3).

``stream_er_submission_grading`` is a drop-in for the existing Dify submit
streamer: it emits the same SSE events and a ``done`` payload whose
``structured_output`` is a ``SubmitResult`` dict so ``er_lab_submission_persistence``
keeps working unchanged.

``stream_er_query`` streams the query (tutor) path.

NOTE: ``build_submit_graph`` and ``build_query_graph`` are imported at *module
scope* so tests can monkeypatch them by attribute
(``monkeypatch.setattr(runner, "build_submit_graph"/"build_query_graph", ...)``).
"""

import base64, json, logging
from typing import Iterator, Optional
from app.services.erd_tutor.submit_graph import build_submit_graph
from app.services.erd_tutor.query_graph import build_query_graph

logger = logging.getLogger(__name__)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


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
        submission_description: Optional[str] = None) -> Iterator[str]:
    def gen() -> Iterator[str]:
        yield _sse("start", {"mode": "Submit", "question_id": question_id})
        try:
            graph = build_submit_graph()
            out = graph.invoke({
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
        last_submit_report: Optional[dict] = None) -> Iterator[str]:
    def gen() -> Iterator[str]:
        yield _sse("start", {"mode": "Query", "question_id": question_id})
        try:
            out = build_query_graph().invoke({
                "mode": "Query", "problem_statement": problem_statement,
                "difficulty": difficulty_label, "rubric_json": rubric_json,
                "student_query": student_query, "image_b64": _image_b64(image_bytes),
                "ibl_stage": ibl_stage, "hint_level": hint_level,
                "current_erd_model": current_erd_model or {},
                "last_submit_report": last_submit_report or {}})
            yield _sse("done", {"mode": "Query", "text": out.get("tutor_text", ""),
                                "structured_output": {"state_update": out.get("state_update", {})}})
        except Exception as exc:
            logger.warning("erd_tutor query failed question_id=%s: %s", question_id, exc)
            yield _sse("error", {"detail": str(exc)})
    return gen()
