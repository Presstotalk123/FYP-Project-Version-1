"""Shared Dify ER submission grading service.

This module owns the Submit-mode grading path that is shared between the
existing ``/api/v1/er-diagram/submission`` endpoint and the upcoming ER lab
submission endpoint. Query-mode (the chat-like streaming path) remains in
``app.api.v1.endpoints.er_diagram`` and re-imports the shared helpers from
this module.
"""

from __future__ import annotations

import io
import json
import logging
import re
import time
from collections import deque
from typing import Any, AsyncIterator, Iterator, Optional, Union
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import HTTPException, UploadFile, status
from pydantic import ValidationError
from starlette.datastructures import Headers

from app.config import settings
from app.schemas.er_diagram import ERSubmissionStructuredOutput
from app.services.erd_tutor import runner as erd_runner

logger = logging.getLogger(__name__)

MAX_ER_IMAGE_BYTES = 5 * 1024 * 1024
RUBRIC_INTERNAL_META_KEY = "__dbassist_meta"
DIFY_SUBMISSION_STREAM_MAX_ATTEMPTS = 2
DIFY_SUBMISSION_RETRY_BACKOFF_SECONDS = 0.4


# ---------------------------------------------------------------------------
# Shared helpers (also imported by app.api.v1.endpoints.er_diagram)
# ---------------------------------------------------------------------------


def _sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_dify_headers(content_type: Optional[str] = None, api_key: Optional[str] = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "DatabaseAssist/1.0",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _format_dify_http_error(stage: str, status_code: int, raw: str) -> HTTPException:
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("detail") or payload
            return HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Dify {stage} failed ({status_code}): {message}",
            )
    except Exception:
        pass

    # Cloudflare often returns HTML. Convert it to a concise actionable message.
    if "cloudflare" in raw.lower():
        cf_code_match = re.search(r"Error\s+(\d{3,4})", raw, re.IGNORECASE)
        ray_match = re.search(r"Ray ID:\s*([A-Za-z0-9]+)", raw, re.IGNORECASE)
        cf_code = cf_code_match.group(1) if cf_code_match else str(status_code)
        ray_id = ray_match.group(1) if ray_match else "unknown"
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Dify {stage} blocked by Cloudflare (error {cf_code}, Ray ID {ray_id}). "
                "This is typically an IP/WAF restriction at api.dify.ai; use an allowed egress IP, "
                "a proxy, or a self-hosted Dify endpoint."
            ),
        )

    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Dify {stage} failed ({status_code})",
    )


def _derive_files_upload_url(workflow_run_url: str) -> str:
    parsed = urlparse(workflow_run_url)
    path = parsed.path.rstrip("/")
    if path.endswith("/workflows/run"):
        path = path[: -len("/workflows/run")] + "/files/upload"
    elif path.endswith("/chat-messages"):
        path = path[: -len("/chat-messages")] + "/files/upload"
    else:
        path = f"{path}/files/upload"
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))


def _strip_rubric_internal_meta(rubric_json: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(rubric_json)
    cleaned.pop(RUBRIC_INTERNAL_META_KEY, None)
    return cleaned


def _parse_json_field(value: str, field_name: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be valid JSON",
        )


def _extract_first_text(value: Any) -> Optional[str]:
    queue: deque[Any] = deque([value])
    scanned = 0
    while queue and scanned < 500:
        current = queue.popleft()
        scanned += 1
        if isinstance(current, str) and current.strip():
            return current.strip()
        if isinstance(current, dict):
            for key in ("text", "answer", "student_message", "response", "message"):
                candidate = current.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    return candidate.strip()
            queue.extend(current.values())
        elif isinstance(current, list):
            queue.extend(current)
    return None


def _upload_file_to_dify(
    upload_file: UploadFile,
    workflow_run_url: str,
    timeout_seconds: int,
    api_key: Optional[str],
    user_ref: str,
) -> str:
    filename = upload_file.filename or "upload"
    content_type = upload_file.content_type or "application/octet-stream"
    file_bytes = upload_file.file.read()
    upload_file.file.seek(0)
    if len(file_bytes) > MAX_ER_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{filename} exceeds {MAX_ER_IMAGE_BYTES // (1024 * 1024)}MB upload limit",
        )
    headers = _build_dify_headers(api_key=api_key)
    upload_url = _derive_files_upload_url(workflow_run_url)

    try:
        with httpx.Client(timeout=float(timeout_seconds)) as client:
            response = client.post(
                upload_url,
                data={"user": user_ref},
                files={"file": (filename, file_bytes, content_type)},
                headers=headers,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unable to reach Dify file upload endpoint: {str(exc)}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected Dify file upload error: {str(exc)}",
        )

    if response.is_error:
        raise _format_dify_http_error("file upload", response.status_code, response.text)

    try:
        payload = response.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify file upload response is not valid JSON",
        )

    upload_id = payload.get("id")
    if not isinstance(upload_id, str) or not upload_id.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify file upload response missing id",
        )
    return upload_id


def _post_dify_workflow_blocking(
    *,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    api_key: Optional[str],
    stage: str,
) -> dict[str, Any]:
    """Call a Dify workflow in blocking mode; return data.outputs as a dict.

    Raises HTTPException(502) on transport errors, non-2xx responses, non-JSON
    bodies, workflow status == failed/error/stopped, or missing data.outputs.
    """
    headers = _build_dify_headers("application/json", api_key)

    try:
        with httpx.Client(timeout=float(timeout_seconds)) as client:
            response = client.post(url, json=payload, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unable to reach Dify endpoint: {str(exc)}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Unexpected Dify integration error: {str(exc)}",
        )

    if response.is_error:
        raise _format_dify_http_error(stage, response.status_code, response.text)

    try:
        body = response.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Dify {stage} returned non-JSON response: {response.text[:500]}"
            ),
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dify {stage} response is not a JSON object",
        )

    # Workflow blocking response shape: {data: {status, outputs, error}}
    data_section = body.get("data")
    if isinstance(data_section, dict):
        status_value = str(data_section.get("status") or "").lower()
        error_value = data_section.get("error")
        if status_value in {"failed", "error", "stopped"}:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    f"Dify workflow failed with status '{status_value}': {error_value}"
                ),
            )
        outputs = data_section.get("outputs")
        if isinstance(outputs, dict):
            return outputs

    # Chat / Agent blocking response shape: {answer: "...", files: [...], ...}
    answer_value = body.get("answer")
    if isinstance(answer_value, str) and answer_value.strip():
        return {"answer": answer_value}

    raise HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"Dify {stage} response missing usable output (no data.outputs or answer)",
    )


# ---------------------------------------------------------------------------
# Submit-mode-only helpers
# ---------------------------------------------------------------------------


def _decode_first_json_value_with_span(raw: str) -> tuple[Optional[Any], Optional[int], Optional[int]]:
    text = raw.lstrip()
    leading_whitespace = len(raw) - len(text)
    if not text:
        return None, None, None

    decoder = json.JSONDecoder()
    try:
        parsed, end = decoder.raw_decode(text)
    except Exception:
        return None, None, None

    return parsed, leading_whitespace, leading_whitespace + end


def _decode_trailing_json_array_with_span(raw: str, min_start: int = 0) -> tuple[Optional[list[Any]], Optional[int], Optional[int]]:
    trimmed_end = len(raw.rstrip())
    if trimmed_end <= min_start:
        return None, None, None

    decoder = json.JSONDecoder()
    best_match: tuple[list[Any], int, int] | None = None

    for start in range(min_start, trimmed_end):
        if raw[start] != "[":
            continue
        try:
            parsed, consumed = decoder.raw_decode(raw[start:trimmed_end])
        except Exception:
            continue
        if start + consumed != trimmed_end or not isinstance(parsed, list):
            continue
        best_match = (parsed, start, trimmed_end)

    if best_match is None:
        return None, None, None

    return best_match


def _normalize_submission_structured_output(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify submission structured_output must be a JSON object",
        )
    return {
        "score": value.get("score"),
        "student_message": value.get("student_message"),
        "checks": value.get("checks"),
    }


def _validate_submission_structured_output(value: Any) -> dict[str, Any]:
    normalized = _normalize_submission_structured_output(value)
    try:
        parsed = ERSubmissionStructuredOutput.model_validate(normalized)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dify submission structured_output schema invalid: {exc.errors()}",
        )

    return parsed.model_dump()


def _parse_submission_answer_text(raw: str) -> dict[str, Any]:
    score, score_start, score_end = _decode_first_json_value_with_span(raw)
    if not isinstance(score, dict) or score_start is None or score_end is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify submission response missing or invalid leading score JSON object",
        )

    checks, checks_start, checks_end = _decode_trailing_json_array_with_span(raw, min_start=score_end)
    if checks is None or checks_start is None or checks_end is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify submission response missing trailing checks JSON array",
        )

    if raw[:score_start].strip() or raw[checks_end:].strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify submission response has unexpected content outside score/message/checks",
        )

    student_message = raw[score_end:checks_start].strip()
    if not student_message:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify submission response missing feedback text between score and checks",
        )

    return _validate_submission_structured_output(
        {
            "score": score,
            "student_message": student_message,
            "checks": checks,
        }
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def _wrap_bytes_as_upload_file(
    image_bytes: bytes,
    *,
    filename: str = "submission.png",
    content_type: str = "image/png",
) -> UploadFile:
    """Wrap raw image bytes in a synthetic UploadFile.

    Used by callers (e.g. the upcoming ER lab submission endpoint) that have
    already persisted the image to their storage provider and only have the
    bytes in hand. ``_upload_file_to_dify`` reads ``upload_file.filename``,
    ``upload_file.content_type``, ``upload_file.file.read()`` and
    ``upload_file.file.seek(0)`` — all of which work against an ``UploadFile``
    backed by ``io.BytesIO`` with a ``content-type`` header set.
    """
    buffer = io.BytesIO(image_bytes)
    return UploadFile(
        file=buffer,
        size=len(image_bytes),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def stream_er_submission_grading(
    *,
    question_id: int,
    problem_statement: str,
    difficulty_label: str,
    rubric_json: str,
    submission_xml_text: Optional[str],
    student_query: Optional[str] = None,
    erd_img: Optional[UploadFile] = None,
    image_bytes: Optional[bytes] = None,
    ibl_stage: str = "orientation",
    hint_level: int = 1,
    last_submit_report: Optional[dict[str, Any]] = None,
    submission_description: Optional[str] = None,
) -> Union[Iterator[str], AsyncIterator[str]]:
    """Stream Submit-mode grading as SSE, dispatching on the configured engine.

    This is the canonical public entrypoint shared by the ER-diagram bank and
    ER-lab submission paths. It selects the grading engine via
    ``settings.ERD_TUTOR_ENGINE``:

    * ``"langgraph"`` -> the local LangGraph engine
      (``app.services.erd_tutor.runner.stream_er_submission_grading``). The
      conversation-state kwargs ``ibl_stage`` / ``hint_level`` /
      ``last_submit_report`` are forwarded to the runner.
    * anything else (default ``"dify"``) -> the legacy hosted Dify path
      (``_stream_er_submission_grading_dify``). The conversation-state kwargs
      are accepted for signature compatibility but ignored, so existing callers
      that don't supply them keep the exact legacy behavior.

    The SSE event sequence (``start`` / ``structured_output`` / ``done`` /
    ``error``) and the ``done`` payload shape are identical across engines so
    downstream consumers (e.g. ``er_lab_submission_persistence``) work
    unchanged.
    """
    if settings.ERD_TUTOR_ENGINE == "langgraph":
        # The LangGraph runner consumes raw bytes, not UploadFile. Bank-mode
        # callers pass only erd_img, so materialize the bytes here — otherwise
        # the vision stage runs imageless and grades an empty diagram.
        if image_bytes is None and erd_img is not None:
            try:
                erd_img.file.seek(0)
            except Exception:
                pass
            image_bytes = erd_img.file.read()
        return erd_runner.stream_er_submission_grading(
            question_id=question_id,
            problem_statement=problem_statement,
            difficulty_label=difficulty_label,
            rubric_json=rubric_json,
            submission_xml_text=submission_xml_text,
            student_query=student_query,
            erd_img=erd_img,
            image_bytes=image_bytes,
            ibl_stage=ibl_stage,
            hint_level=hint_level,
            last_submit_report=last_submit_report,
            submission_description=submission_description,
        )

    # Legacy Dify path — ignores the conversation-state kwargs.
    return _stream_er_submission_grading_dify(
        question_id=question_id,
        problem_statement=problem_statement,
        difficulty_label=difficulty_label,
        rubric_json=rubric_json,
        submission_xml_text=submission_xml_text,
        student_query=student_query,
        erd_img=erd_img,
        image_bytes=image_bytes,
    )


def _stream_er_submission_grading_dify(
    *,
    question_id: int,
    problem_statement: str,
    difficulty_label: str,
    rubric_json: str,
    submission_xml_text: Optional[str],
    student_query: Optional[str] = None,
    erd_img: Optional[UploadFile] = None,
    image_bytes: Optional[bytes] = None,
) -> Iterator[str]:
    """Stream Dify Submit-mode grading as SSE-formatted strings.

    Yields SSE events: ``start``, ``structured_output``, ``done`` on success
    or ``error`` on failure. The caller decides whether to persist a row
    based on whether a ``done`` event was emitted.

    ``student_query`` is typically empty for Submit-mode (which is graded
    rather than chat-driven) but is preserved here for fidelity with the
    pre-refactor ``/api/v1/er-diagram/submission`` endpoint, which forwarded
    any client-supplied value through to Dify as the ``Student_Query`` input.

    ``image_bytes`` is an alternative to ``erd_img`` for callers that have
    already buffered the image (e.g. after persisting it to a storage
    provider). When supplied (and ``erd_img`` is ``None``), the bytes are
    wrapped in a synthetic ``UploadFile`` before being uploaded to Dify.
    """
    if not settings.DIFY_ER_SUBMISSION_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DIFY_ER_SUBMISSION_URL is not configured",
        )

    effective_upload: Optional[UploadFile] = erd_img
    if effective_upload is None and image_bytes is not None:
        effective_upload = _wrap_bytes_as_upload_file(image_bytes)

    files: list[dict[str, str]] = []
    erd_img_input: Any = ""
    if effective_upload is not None:
        upload_file_id = _upload_file_to_dify(
            upload_file=effective_upload,
            workflow_run_url=settings.DIFY_ER_SUBMISSION_URL,
            timeout_seconds=settings.DIFY_ER_SUBMISSION_TIMEOUT_SECONDS,
            api_key=settings.DIFY_ER_SUBMISSION_API_KEY,
            user_ref=f"databaseassist-er-submission-{question_id}",
        )
        file_ref = {
            "type": "image",
            "transfer_method": "local_file",
            "upload_file_id": upload_file_id,
        }
        erd_img_input = file_ref
        files.append(file_ref)

    rubric = _parse_json_field(rubric_json, "rubric_json")
    if not isinstance(rubric, dict):
        rubric = {}
    rubric_text = json.dumps(_strip_rubric_internal_meta(rubric), ensure_ascii=False)

    mode = "Submit"
    # Submit-mode never carries a free-form student question; preserve the
    # default chat_query previously used by the inline implementation so the
    # Dify workflow input shape is identical.
    chat_query = "Please evaluate this ER diagram submission."

    workflow_payload = {
        "inputs": {
            "Problem_Statement": problem_statement,
            "Problem_Difficulty": difficulty_label,
            "Rubric": rubric_text,
            "ERD_Img": erd_img_input,
            "Submission_Xml_Text": (submission_xml_text or "").strip(),
            "Student_Query": (student_query or "").strip(),
            "Mode": mode,
        },
        "query": chat_query,
        "response_mode": "streaming",
        "user": f"databaseassist-er-submission-{question_id}",
        "files": files,
    }

    def stream_generator() -> Iterator[str]:
        start_time = time.perf_counter()
        logger.info("submission_stream_started question_id=%s mode=%s", question_id, mode)
        yield _sse_event(
            "start",
            {
                "mode": mode,
                "question_id": question_id,
            },
        )

        submit_payload = {**workflow_payload, "response_mode": "blocking"}

        for attempt in range(1, DIFY_SUBMISSION_STREAM_MAX_ATTEMPTS + 1):
            try:
                outputs = _post_dify_workflow_blocking(
                    url=settings.DIFY_ER_SUBMISSION_URL,
                    payload=submit_payload,
                    timeout_seconds=settings.DIFY_ER_SUBMISSION_TIMEOUT_SECONDS,
                    api_key=settings.DIFY_ER_SUBMISSION_API_KEY,
                    stage="submission request",
                )

                answer_text = _extract_first_text(outputs) or ""
                if not answer_text.strip():
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Dify submission response missing final grading payload",
                    )

                structured_output = _parse_submission_answer_text(answer_text)
                yield _sse_event(
                    "structured_output",
                    {"structured_output": structured_output},
                )

                student_message = str(structured_output.get("student_message") or "").strip()
                if not student_message:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Dify submission structured_output missing student_message",
                    )

                done_payload = {
                    "mode": mode,
                    "text": student_message,
                    "structured_output": structured_output,
                }
                yield _sse_event("done", done_payload)
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                logger.info(
                    "submission_stream_completed question_id=%s mode=%s duration_ms=%s text_len=%s attempt=%s",
                    question_id,
                    mode,
                    duration_ms,
                    len(student_message),
                    attempt,
                )
                return
            except HTTPException as exc:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                logger.warning(
                    "submission_stream_failed question_id=%s mode=%s duration_ms=%s detail=%s attempt=%s",
                    question_id,
                    mode,
                    duration_ms,
                    exc.detail,
                    attempt,
                )
                yield _sse_event("error", {"detail": str(exc.detail)})
                return
            except httpx.RequestError as exc:
                if attempt < DIFY_SUBMISSION_STREAM_MAX_ATTEMPTS:
                    logger.warning(
                        "submission_stream_retry question_id=%s mode=%s attempt=%s/%s detail=%s",
                        question_id,
                        mode,
                        attempt,
                        DIFY_SUBMISSION_STREAM_MAX_ATTEMPTS,
                        str(exc),
                    )
                    time.sleep(DIFY_SUBMISSION_RETRY_BACKOFF_SECONDS * attempt)
                    continue

                duration_ms = int((time.perf_counter() - start_time) * 1000)
                message = (
                    "Unable to reach Dify submission endpoint after retries: "
                    f"{str(exc)}"
                )
                logger.warning(
                    "submission_stream_failed question_id=%s mode=%s duration_ms=%s detail=%s attempt=%s",
                    question_id,
                    mode,
                    duration_ms,
                    message,
                    attempt,
                )
                yield _sse_event("error", {"detail": message})
                return
            except Exception as exc:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                message = f"Unexpected Dify submission integration error: {str(exc)}"
                logger.exception(
                    "submission_stream_failed question_id=%s mode=%s duration_ms=%s attempt=%s",
                    question_id,
                    mode,
                    duration_ms,
                    attempt,
                )
                yield _sse_event("error", {"detail": message})
                return

    return stream_generator()
