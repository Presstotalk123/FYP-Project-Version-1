import asyncio
import json
import logging
import re
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.core.cache import cache_read, Ns
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.user import User, UserRole
from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.schemas.er_diagram import (
    DifficultyLabel,
    ERDiagramQuestionResponse,
    ERDiagramQuestionListItem,
    ERDiagramQuestionCountResponse,
    GenerateRubricMode,
    GenerateRubricResponse,
    ERSubmissionMode,
)
from app.services.er_grading import (
    DIFY_SUBMISSION_RETRY_BACKOFF_SECONDS,
    DIFY_SUBMISSION_STREAM_MAX_ATTEMPTS,
    RUBRIC_INTERNAL_META_KEY,
    _build_dify_headers,
    _extract_first_text,
    _format_dify_http_error,
    _parse_json_field,
    _sse_event,
    _strip_rubric_internal_meta,
    _upload_file_to_dify,
    stream_er_submission_grading,
)
from app.services.erd_rubric import runner as erd_rubric_runner
from app.utils.er_storage import get_er_storage_provider

router = APIRouter(prefix="/er-diagram", tags=["er-diagram"])
logger = logging.getLogger(__name__)


def _er_question_accessible_via_assessment(question_id: int, user_id: int, db: Session) -> bool:
    """Return True if the student has an active session in a running assessment that contains this
    ER question. Mirrors labs._lab_accessible_via_assessment — assessment content is cloned
    (owner_assessment_id set, is_published=0) and AssessmentItem.item_id is repointed to the clone,
    so a participant is authorized while a random ID-guesser is not."""
    result = (
        db.query(AssessmentSession)
        .join(Assessment, Assessment.id == AssessmentSession.assessment_id)
        .join(AssessmentItem, AssessmentItem.assessment_id == Assessment.id)
        .filter(
            AssessmentSession.user_id == user_id,
            AssessmentSession.is_active == 1,
            Assessment.is_running == 1,
            AssessmentItem.item_id == question_id,
            AssessmentItem.item_type == "er_question",
        )
        .first()
    )
    return result is not None
MAX_ER_XML_CHARS = 500_000
MAX_ER_DESC_CHARS = 5_000
RUBRIC_REQUIRED_OUTPUT_KEYS = frozenset({"difficulty", "rubric_json", "rubric_md", "diff_summary"})
SHOW_RUBRIC_ON_ATTEMPT_KEY = "show_rubric_on_attempt"


def _looks_like_template_placeholder(value: str) -> bool:
    normalized = value.strip()
    # Reject unresolved placeholders only when the whole field is a token.
    return bool(re.fullmatch(r"\{\{\s*[\w.-]+\s*\}\}|\[[\w.-]+\]|<[\w.-]+>", normalized))


def _extract_show_rubric_on_attempt(rubric_json: dict[str, Any]) -> bool:
    internal_meta = rubric_json.get(RUBRIC_INTERNAL_META_KEY)
    if not isinstance(internal_meta, dict):
        return False

    raw_value = internal_meta.get(SHOW_RUBRIC_ON_ATTEMPT_KEY)
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        return raw_value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(raw_value, (int, float)):
        return raw_value != 0
    return False


def _with_rubric_visibility_meta(rubric_json: dict[str, Any], show_rubric_on_attempt: bool) -> dict[str, Any]:
    merged = dict(rubric_json)
    internal_meta = merged.get(RUBRIC_INTERNAL_META_KEY)
    if not isinstance(internal_meta, dict):
        internal_meta = {}
    internal_meta[SHOW_RUBRIC_ON_ATTEMPT_KEY] = bool(show_rubric_on_attempt)
    merged[RUBRIC_INTERNAL_META_KEY] = internal_meta
    return merged


def _post_dify_json(
    *,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    api_key: Optional[str],
    stage: str,
) -> dict[str, Any]:
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
        payload_json = response.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify response is not valid JSON",
        )

    if not isinstance(payload_json, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify response must be a JSON object",
        )
    return payload_json


def _extract_dify_workflow_outputs(payload: dict[str, Any]) -> dict[str, Any]:
    outputs = payload
    data_section = payload.get("data")
    if isinstance(data_section, dict):
        status_value = data_section.get("status")
        error_value = data_section.get("error")
        if status_value and status_value != "succeeded":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Dify workflow failed with status '{status_value}': {error_value}",
            )
        nested_outputs = data_section.get("outputs")
        if isinstance(nested_outputs, dict):
            outputs = nested_outputs

    if not isinstance(outputs, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify workflow outputs must be a JSON object",
        )
    return outputs


def _extract_workflow_outputs_from_stream_payload(payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    data_section = payload.get("data")
    if isinstance(data_section, dict):
        status_value = str(data_section.get("status") or "").lower()
        error_value = data_section.get("error")
        if status_value in {"failed", "error", "stopped"}:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Dify workflow failed with status '{status_value}': {error_value}",
            )
        nested_outputs = data_section.get("outputs")
        if isinstance(nested_outputs, dict):
            return nested_outputs

    top_outputs = payload.get("outputs")
    if isinstance(top_outputs, dict):
        return top_outputs
    return None


def _post_dify_workflow_stream_outputs(
    *,
    url: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    api_key: Optional[str],
    stage: str,
) -> dict[str, Any]:
    headers = _build_dify_headers("application/json", api_key)
    headers["Accept"] = "text/event-stream"
    latest_outputs: Optional[dict[str, Any]] = None
    parse_failures = 0

    try:
        with httpx.Client(timeout=float(timeout_seconds)) as client:
            with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.is_error:
                    raw = response.read().decode("utf-8", errors="ignore")
                    raise _format_dify_http_error(stage, response.status_code, raw)

                content_type = (response.headers.get("content-type") or "").lower()
                if "text/event-stream" not in content_type:
                    raw = response.read().decode("utf-8", errors="ignore")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=(
                            "Dify rubric stream protocol error. "
                            f"Expected text/event-stream, got '{content_type or 'unknown'}'. "
                            f"Response: {raw[:500]}"
                        ),
                    )

                for line in response.iter_lines():
                    if line is None:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8", errors="ignore")
                    stripped = line.strip()
                    if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
                        continue

                    data_text = stripped[5:].strip()
                    if not data_text or data_text == "[DONE]":
                        continue

                    try:
                        stream_payload = json.loads(data_text)
                    except Exception:
                        parse_failures += 1
                        if parse_failures >= 5:
                            raise HTTPException(
                                status_code=status.HTTP_502_BAD_GATEWAY,
                                detail="Dify rubric stream returned repeated invalid JSON frames",
                            )
                        continue

                    parse_failures = 0
                    if not isinstance(stream_payload, dict):
                        continue

                    event_name = str(stream_payload.get("event") or "").lower()
                    if event_name == "error":
                        message = _extract_first_text(stream_payload) or stream_payload.get("message") or "Unknown stream error"
                        raise HTTPException(
                            status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"Dify rubric stream failed: {message}",
                        )

                    maybe_outputs = _extract_workflow_outputs_from_stream_payload(stream_payload)
                    if isinstance(maybe_outputs, dict):
                        latest_outputs = maybe_outputs

                    if event_name in {"message_end", "workflow_finished", "agent_message_end", "done"}:
                        break
    except HTTPException:
        raise
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

    if not isinstance(latest_outputs, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify rubric stream completed without workflow outputs",
        )
    return latest_outputs


def _append_stream_text(existing: str, candidate: Optional[str]) -> tuple[str, Optional[str]]:
    if not candidate:
        return existing, None

    if not existing:
        return candidate, candidate
    if candidate == existing or existing.endswith(candidate):
        return existing, None
    if candidate.startswith(existing):
        chunk = candidate[len(existing) :]
        return candidate, chunk or None
    return existing + candidate, candidate


def _extract_stream_text_chunk(payload: dict[str, Any]) -> Optional[str]:
    for key in ("answer", "delta", "text", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _upload_model_answer_to_dify(model_answer: UploadFile) -> str:
    return _upload_file_to_dify(
        upload_file=model_answer,
        workflow_run_url=settings.DIFY_ER_RUBRIC_URL or "",
        timeout_seconds=settings.DIFY_ER_RUBRIC_TIMEOUT_SECONDS,
        api_key=settings.DIFY_ER_RUBRIC_API_KEY,
        user_ref="databaseassist-er-rubric",
    )


def _call_dify_generate_rubric(
    mode: GenerateRubricMode,
    notation: str,
    problem_statement: str,
    refinement_instruction: Optional[str],
    rubric_previous: Optional[str],
    instruction_history: Optional[str],
    model_answer: Optional[UploadFile],
) -> dict[str, Any]:
    if not settings.DIFY_ER_RUBRIC_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DIFY_ER_RUBRIC_URL is not configured",
        )

    parsed_rubric_previous: dict[str, Any] | None = None
    parsed_instruction_history: list[str] | None = None
    if rubric_previous:
        try:
            loaded_previous = json.loads(rubric_previous)
            if isinstance(loaded_previous, dict):
                parsed_rubric_previous = loaded_previous
        except Exception:
            parsed_rubric_previous = None
    if instruction_history:
        try:
            loaded_history = json.loads(instruction_history)
            if isinstance(loaded_history, list):
                parsed_instruction_history = [str(item) for item in loaded_history]
        except Exception:
            parsed_instruction_history = None

    files: list[dict[str, str]] = []
    model_answer_input: Any = ""
    if model_answer:
        upload_file_id = _upload_model_answer_to_dify(model_answer)
        file_ref = {
            "type": "image",
            "transfer_method": "local_file",
            "upload_file_id": upload_file_id,
        }
        model_answer_input = file_ref
        files.append(file_ref)

    effective_rubric_previous = parsed_rubric_previous or {}
    effective_instruction_history = parsed_instruction_history or []
    effective_instruction_history_dict = {"history": effective_instruction_history}
    effective_refinement = refinement_instruction or ""

    workflow_payload = {
        "inputs": {
            "Mode": mode,
            "mode": mode,
            "Notation": notation,
            "Problem_Statement": problem_statement,
            "problem_statement": problem_statement,
            "Refinement_Instruction": effective_refinement,
            "Rubric_Previous": effective_rubric_previous,
            "Instruction_History": effective_instruction_history_dict,
            "Model_Answer": model_answer_input,
        },
        "response_mode": "streaming",
        "user": "databaseassist-er-rubric",
        "files": files,
    }

    # Some existing Dify workflows still read legacy key names in Pascal/snake variants.
    outputs = _post_dify_workflow_stream_outputs(
        url=settings.DIFY_ER_RUBRIC_URL,
        payload=workflow_payload,
        timeout_seconds=settings.DIFY_ER_RUBRIC_TIMEOUT_SECONDS,
        api_key=settings.DIFY_ER_RUBRIC_API_KEY,
        stage="rubric request",
    )
    output_keys = set(outputs.keys()) if isinstance(outputs, dict) else set()
    missing_keys = sorted(RUBRIC_REQUIRED_OUTPUT_KEYS - output_keys)
    unexpected_keys = sorted(output_keys - RUBRIC_REQUIRED_OUTPUT_KEYS)
    if missing_keys or unexpected_keys:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Dify response output keys invalid. "
                f"Missing: {missing_keys}; Unexpected: {unexpected_keys}; Observed: {sorted(output_keys)}"
            ),
        )

    rubric_md = outputs.get("rubric_md") if isinstance(outputs, dict) else None
    if not isinstance(rubric_md, str) or not rubric_md.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dify response has invalid rubric_md. Available output keys: {sorted(output_keys)}",
        )

    difficulty = outputs.get("difficulty") if isinstance(outputs, dict) else None
    if not isinstance(difficulty, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dify response missing difficulty object. Available output keys: {sorted(output_keys)}",
        )

    label = difficulty.get("label")
    rationale = difficulty.get("rationale")
    if label not in {"Easy", "Medium", "Hard"} or not isinstance(rationale, str) or not rationale.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify response has invalid difficulty payload",
        )

    rubric_json = outputs.get("rubric_json") if isinstance(outputs, dict) else None
    if not isinstance(rubric_json, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify response rubric_json must be an object",
        )

    diff_summary = outputs.get("diff_summary") if isinstance(outputs, dict) else None
    if not isinstance(diff_summary, list):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify response diff_summary must be an array",
        )

    return {
        "difficulty": {
            "label": label,
            "rationale": rationale.strip(),
        },
        "rubric_json": rubric_json,
        "rubric_md": rubric_md,
        "diff_summary": diff_summary,
    }


def _call_dify_er_submission(
    question: ERDiagramQuestion,
    mode: ERSubmissionMode,
    student_query: Optional[str],
    submission_xml_text: Optional[str],
    erd_img: Optional[UploadFile],
) -> Any:
    if mode == "Submit":
        # Submit-mode is shared with the upcoming ER lab submission endpoint —
        # see app.services.er_grading for the canonical implementation.
        return stream_er_submission_grading(
            question_id=question.id,
            problem_statement=question.problem_statement,
            difficulty_label=question.difficulty_label,
            rubric_json=question.rubric_json,
            submission_xml_text=submission_xml_text,
            student_query=student_query,
            erd_img=erd_img,
        )

    if not settings.DIFY_ER_SUBMISSION_URL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DIFY_ER_SUBMISSION_URL is not configured",
        )

    files: list[dict[str, str]] = []
    erd_img_input: Any = ""
    if erd_img:
        upload_file_id = _upload_file_to_dify(
            upload_file=erd_img,
            workflow_run_url=settings.DIFY_ER_SUBMISSION_URL,
            timeout_seconds=settings.DIFY_ER_SUBMISSION_TIMEOUT_SECONDS,
            api_key=settings.DIFY_ER_SUBMISSION_API_KEY,
            user_ref=f"databaseassist-er-submission-{question.id}",
        )
        file_ref = {
            "type": "image",
            "transfer_method": "local_file",
            "upload_file_id": upload_file_id,
        }
        erd_img_input = file_ref
        files.append(file_ref)

    rubric = _parse_json_field(question.rubric_json, "rubric_json")
    if not isinstance(rubric, dict):
        rubric = {}
    rubric_text = json.dumps(_strip_rubric_internal_meta(rubric), ensure_ascii=False)

    chat_query = ((student_query or "").strip() if mode == "Query" else "")
    if not chat_query:
        chat_query = "Please evaluate this ER diagram submission."

    workflow_payload = {
        "inputs": {
            "Problem_Statement": question.problem_statement,
            "Problem_Difficulty": question.difficulty_label,
            "Rubric": rubric_text,
            "ERD_Img": erd_img_input,
            "Submission_Xml_Text": (submission_xml_text or "").strip(),
            "Student_Query": (student_query or "").strip(),
            "Mode": mode,
        },
        "query": chat_query,
        "response_mode": "streaming",
        "user": f"databaseassist-er-submission-{question.id}",
        "files": files,
    }

    headers = _build_dify_headers("application/json", settings.DIFY_ER_SUBMISSION_API_KEY)
    headers["Accept"] = "text/event-stream"

    def stream_generator():
        start_time = time.perf_counter()
        logger.info("submission_stream_started question_id=%s mode=%s", question.id, mode)
        yield _sse_event(
            "start",
            {
                "mode": mode,
                "question_id": question.id,
            },
        )

        for attempt in range(1, DIFY_SUBMISSION_STREAM_MAX_ATTEMPTS + 1):
            accumulated_text = ""
            parse_failures = 0
            fallback_text: Optional[str] = None

            try:
                with httpx.Client(timeout=float(settings.DIFY_ER_SUBMISSION_TIMEOUT_SECONDS)) as client:
                    with client.stream(
                        "POST",
                        settings.DIFY_ER_SUBMISSION_URL,
                        json=workflow_payload,
                        headers=headers,
                    ) as response:
                        if response.is_error:
                            raw = response.read().decode("utf-8", errors="ignore")
                            raise _format_dify_http_error("submission request", response.status_code, raw)

                        content_type = (response.headers.get("content-type") or "").lower()
                        if "text/event-stream" not in content_type:
                            raw = response.read().decode("utf-8", errors="ignore")
                            raise HTTPException(
                                status_code=status.HTTP_502_BAD_GATEWAY,
                                detail=(
                                    "Dify submission stream protocol error. "
                                    f"Expected text/event-stream, got '{content_type or 'unknown'}'. "
                                    f"Response: {raw[:500]}"
                                ),
                            )

                        for line in response.iter_lines():
                            if line is None:
                                continue
                            if isinstance(line, bytes):
                                line = line.decode("utf-8", errors="ignore")
                            stripped = line.strip()
                            if not stripped or stripped.startswith(":") or not stripped.startswith("data:"):
                                continue

                            data_text = stripped[5:].strip()
                            if not data_text or data_text == "[DONE]":
                                continue

                            try:
                                payload = json.loads(data_text)
                            except Exception:
                                parse_failures += 1
                                if parse_failures >= 5:
                                    raise HTTPException(
                                        status_code=status.HTTP_502_BAD_GATEWAY,
                                        detail="Dify submission stream returned repeated invalid JSON frames",
                                    )
                                continue

                            parse_failures = 0
                            if not isinstance(payload, dict):
                                continue

                            event_name = str(payload.get("event") or "").lower()
                            if event_name == "error":
                                message = _extract_first_text(payload) or payload.get("message") or "Unknown stream error"
                                raise HTTPException(
                                    status_code=status.HTTP_502_BAD_GATEWAY,
                                    detail=f"Dify submission stream failed: {message}",
                                )

                            stream_text_chunk = _extract_stream_text_chunk(payload)
                            next_text, chunk = _append_stream_text(accumulated_text, stream_text_chunk)
                            if chunk:
                                accumulated_text = next_text
                                yield _sse_event(
                                    "token",
                                    {
                                        "chunk": chunk,
                                        "text": accumulated_text,
                                    },
                                )

                            first_text_candidate = _extract_first_text(payload)
                            if first_text_candidate:
                                fallback_text = first_text_candidate

                            if event_name in {"message_end", "workflow_finished", "agent_message_end", "done"}:
                                break

                final_text = accumulated_text or fallback_text or "No response text returned from submission workflow."
                done_payload = {
                    "mode": mode,
                    "text": final_text,
                    "structured_output": None,
                }
                yield _sse_event("done", done_payload)
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                logger.info(
                    "submission_stream_completed question_id=%s mode=%s duration_ms=%s text_len=%s attempt=%s",
                    question.id,
                    mode,
                    duration_ms,
                    len(final_text),
                    attempt,
                )
                return
            except HTTPException as exc:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                logger.warning(
                    "submission_stream_failed question_id=%s mode=%s duration_ms=%s detail=%s attempt=%s",
                    question.id,
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
                        question.id,
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
                    question.id,
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
                    question.id,
                    mode,
                    duration_ms,
                    attempt,
                )
                yield _sse_event("error", {"detail": message})
                return

    return stream_generator()


def _to_response(
    question: ERDiagramQuestion,
    *,
    hide_rubric_when_disabled: bool = True,
    attempt_count: int | None = None,
) -> ERDiagramQuestionResponse:
    rubric_json = _parse_json_field(question.rubric_json, "rubric_json")
    instruction_history = _parse_json_field(question.instruction_history_json, "instruction_history")

    show_rubric_on_attempt = False
    if not isinstance(rubric_json, dict):
        rubric_json = {}
    else:
        show_rubric_on_attempt = _extract_show_rubric_on_attempt(rubric_json)
        rubric_json = _strip_rubric_internal_meta(rubric_json)
    if not isinstance(instruction_history, list):
        instruction_history = []

    instruction_history = [str(item) for item in instruction_history if str(item).strip()]
    rubric_md_value: str | None = question.rubric_md
    rubric_json_value: dict[str, Any] | None = rubric_json
    if hide_rubric_when_disabled and not show_rubric_on_attempt:
        rubric_md_value = None
        rubric_json_value = None

    return ERDiagramQuestionResponse(
        id=question.id,
        title=question.title,
        problem_statement=question.problem_statement,
        notation=question.notation,
        difficulty_label=question.difficulty_label,
        difficulty_rationale=question.difficulty_rationale,
        rubric_md=rubric_md_value,
        rubric_json=rubric_json_value,
        instruction_history=instruction_history,
        show_rubric_on_attempt=show_rubric_on_attempt,
        model_answer_storage_key=question.model_answer_storage_key,
        model_answer_url=question.model_answer_url,
        created_by=question.created_by,
        created_at=question.created_at,
        updated_at=question.updated_at,
        is_published=bool(question.is_published),
        attempt_count=attempt_count,
    )


def _count_graded_attempts(db: Session, question_id: int) -> int:
    """How many students have already been graded on this question.

    One ERD-tutor conversation exists per user per question, so conversations
    carrying a submit report are exactly the students who have submitted. Only
    meaningful on the LangGraph engine; the Dify path records no conversations
    and this correctly reports 0.
    """
    from app.models.erd_tutor_conversation import ErdTutorConversation

    return (
        db.query(ErdTutorConversation)
        .filter(
            ErdTutorConversation.er_diagram_question_id == question_id,
            ErdTutorConversation.last_submit_report.isnot(None),
        )
        .count()
    )


async def _generate_rubric_payload(
    *,
    mode,
    notation: str,
    problem_statement: str,
    refinement_instruction,
    rubric_previous,
    instruction_history,
    model_answer,
) -> dict:
    """Dispatch rubric generation on settings.ERD_RUBRIC_ENGINE. Returns the
    {difficulty, rubric_json, rubric_md, diff_summary} dict from either engine."""
    if settings.ERD_RUBRIC_ENGINE == "langgraph":
        image_bytes = None
        if model_answer is not None:
            try:
                model_answer.file.seek(0)
            except Exception:
                pass
            image_bytes = model_answer.file.read()
        try:
            return await erd_rubric_runner.generate_rubric(
                mode=mode,
                notation=notation,
                problem_statement=problem_statement,
                refinement_instruction=refinement_instruction,
                rubric_previous=rubric_previous,
                instruction_history=instruction_history,
                image_bytes=image_bytes,
            )
        except HTTPException:
            raise
        except Exception as exc:  # parity with the Dify path's 502 contract
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Rubric generation failed: {exc}",
            ) from exc
    # Legacy Dify path is a blocking httpx call; offload it so the async endpoint
    # doesn't block the event loop (it keeps its own timeouts/retries internally).
    return await asyncio.to_thread(
        lambda: _call_dify_generate_rubric(
            mode=mode,
            notation=notation,
            problem_statement=problem_statement,
            refinement_instruction=refinement_instruction,
            rubric_previous=rubric_previous,
            instruction_history=instruction_history,
            model_answer=model_answer,
        )
    )


@router.post("/rubric/generate", response_model=GenerateRubricResponse)
async def generate_er_rubric(
    mode: GenerateRubricMode = Form(...),
    notation: str = Form("Chen"),
    problem_title: str = Form(...),
    problem_statement: str = Form(...),
    model_answer: Optional[UploadFile] = File(None),
    refinement_instruction: Optional[str] = Form(None),
    rubric_previous: Optional[str] = Form(None),
    instruction_history: Optional[str] = Form(None),
    _: User = Depends(get_current_user),
):
    title = problem_title.strip()
    statement = problem_statement.strip()
    refinement = refinement_instruction.strip() if refinement_instruction else None

    if notation != "Chen":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="notation must be Chen",
        )

    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="problem_title cannot be empty",
        )

    if not statement:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="problem_statement cannot be empty",
        )
    if _looks_like_template_placeholder(statement):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="problem_statement appears to be a template placeholder; provide concrete text",
        )

    if mode == "patch":
        if not refinement:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="refinement_instruction is required when mode is patch",
            )
        if not rubric_previous:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rubric_previous is required when mode is patch",
            )
        if not instruction_history:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="instruction_history is required when mode is patch",
            )

        parsed_history = _parse_json_field(instruction_history, "instruction_history")
        if not isinstance(parsed_history, list):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="instruction_history must be a JSON array",
            )
        if not parsed_history:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="instruction_history cannot be empty when mode is patch",
            )

    if model_answer and (not model_answer.content_type or not model_answer.content_type.startswith("image/")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="model_answer must be an image file",
        )

    rubric_payload = await _generate_rubric_payload(
        mode=mode,
        notation=notation,
        problem_statement=statement,
        refinement_instruction=refinement,
        rubric_previous=rubric_previous,
        instruction_history=instruction_history,
        model_answer=model_answer,
    )

    return GenerateRubricResponse(**rubric_payload)


@router.post("/questions", response_model=ERDiagramQuestionResponse, status_code=status.HTTP_201_CREATED)
def create_er_question(
    title: str = Form(...),
    problem_statement: str = Form(...),
    notation: str = Form("Chen"),
    difficulty_label: DifficultyLabel = Form(...),
    difficulty_rationale: str = Form(...),
    rubric_md: str = Form(...),
    rubric_json: str = Form("{}"),
    instruction_history: str = Form("[]"),
    show_rubric_on_attempt: bool = Form(False),
    model_answer: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Student authoring is opt-in: staff turn it on from Settings. Existing
    # student-created questions are unaffected — this gates creation only.
    if current_user.role not in {UserRole.STAFF, UserRole.ADMIN}:
        from app.services import app_settings as settings_service

        if not settings_service.get_bool(db, settings_service.ERD_STUDENT_AUTHORING):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Students cannot create ER questions. Ask your instructor to enable it in Settings.",
            )

    parsed_rubric_json = _parse_json_field(rubric_json, "rubric_json")
    parsed_instruction_history = _parse_json_field(instruction_history, "instruction_history")

    if notation != "Chen":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="notation must be Chen",
        )

    cleaned_title = title.strip()
    cleaned_statement = problem_statement.strip()
    cleaned_rubric = rubric_md.strip()
    cleaned_rationale = difficulty_rationale.strip()

    if not cleaned_title:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")
    if not cleaned_statement:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="problem_statement is required")
    if not cleaned_rubric:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rubric_md is required")
    if not cleaned_rationale:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="difficulty_rationale is required")
    if not isinstance(parsed_rubric_json, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rubric_json must be a JSON object")
    if not isinstance(parsed_instruction_history, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="instruction_history must be a JSON array",
        )

    cleaned_history = [str(item).strip() for item in parsed_instruction_history if str(item).strip()]
    persisted_rubric_json = _with_rubric_visibility_meta(parsed_rubric_json, show_rubric_on_attempt)

    model_answer_storage_key = None
    model_answer_url = None
    if model_answer:
        if not model_answer.content_type or not model_answer.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="model_answer must be an image file",
            )
        try:
            storage = get_er_storage_provider()
            model_answer_storage_key, model_answer_url = storage.save(model_answer)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to store model_answer: {str(exc)}",
            )

    question = ERDiagramQuestion(
        title=cleaned_title,
        problem_statement=cleaned_statement,
        notation=notation,
        difficulty_label=difficulty_label,
        difficulty_rationale=cleaned_rationale,
        rubric_md=cleaned_rubric,
        rubric_json=json.dumps(persisted_rubric_json),
        instruction_history_json=json.dumps(cleaned_history),
        model_answer_storage_key=model_answer_storage_key,
        model_answer_url=model_answer_url,
        created_by=current_user.id,
    )
    db.add(question)
    db.commit()
    db.refresh(question)

    return _to_response(question)


@router.get("/questions", response_model=list[ERDiagramQuestionListItem])
def list_er_questions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Identical across all staff/admin (and, per role, across all students), so cached
    # in-process and invalidated on any ERDiagramQuestion mutation (see app/core/cache.py).
    is_student = current_user.role.value == "student"
    role = "student" if is_student else "staff"

    def producer():
        question_rows = (
            db.query(ERDiagramQuestion, User.role)
            .join(User, ERDiagramQuestion.created_by == User.id)
            # Exclude assessment-owned clones (owner_assessment_id set) from the ER bank/picker.
            .filter(
                ERDiagramQuestion.is_deleted == 0,
                ERDiagramQuestion.owner_assessment_id.is_(None),
            )
            .order_by(ERDiagramQuestion.created_at.desc())
            .all()
        )

        items: list[ERDiagramQuestionListItem] = []
        for question, creator_role in question_rows:
            role_value = creator_role.value if isinstance(creator_role, UserRole) else str(creator_role).strip().lower()
            if role_value not in {"student", "staff", "admin"}:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Invalid creator role '{creator_role}' for ER question id={question.id}",
                )

            # Publish gate applies only to staff-created ER questions. Student-created ones stay
            # visible to students as before, so students never lose sight of their own creations.
            if is_student and role_value in {"staff", "admin"} and not question.is_published:
                continue

            items.append(
                ERDiagramQuestionListItem(
                    id=question.id,
                    title=question.title,
                    problem_statement=question.problem_statement[:200].strip(),
                    difficulty_label=question.difficulty_label,
                    created_by=question.created_by,
                    created_by_role=role_value,
                    created_at=question.created_at,
                    is_published=bool(question.is_published),
                )
            )

        return items

    return cache_read(
        db,
        Ns.ER_QUESTIONS,
        key=(f"role={role}",),
        producer=producer,
    )


@router.get("/questions/count", response_model=ERDiagramQuestionCountResponse)
def get_er_question_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Dashboard counts for standalone ERD practice questions.

    `total` is the size of the visible ER-question bank — cached in-process under
    Ns.ER_QUESTIONS (auto-invalidated on any ERDiagramQuestion mutation), identical
    across users of a role. `attempted` is per-user and computed live. Declared
    before `/questions/{question_id}` so the literal path is matched first.
    """
    is_student = current_user.role.value == "student"
    role = "student" if is_student else "staff"

    def producer() -> int:
        # Mirror list_er_questions' visibility: exclude deleted + assessment clones;
        # students additionally see staff/admin questions only once published, but
        # all student-created ones regardless of publish state.
        query = (
            db.query(ERDiagramQuestion)
            .join(User, ERDiagramQuestion.created_by == User.id)
            .filter(
                ERDiagramQuestion.is_deleted == 0,
                ERDiagramQuestion.owner_assessment_id.is_(None),
            )
        )
        if is_student:
            query = query.filter(
                or_(User.role == UserRole.STUDENT, ERDiagramQuestion.is_published == 1)
            )
        return query.count()

    total = cache_read(db, Ns.ER_QUESTIONS, key=("count", role), producer=producer)

    # One standalone conversation row per (user, question); last_submit_score is set
    # once a submission has been graded — that is the "attempted" signal. Join to the
    # question so deleted questions never inflate the count.
    attempted = (
        db.query(ErdTutorConversation)
        .join(
            ERDiagramQuestion,
            ERDiagramQuestion.id == ErdTutorConversation.er_diagram_question_id,
        )
        .filter(
            ErdTutorConversation.user_id == current_user.id,
            ErdTutorConversation.context_type == "standalone",
            ErdTutorConversation.er_diagram_question_id.isnot(None),
            ErdTutorConversation.last_submit_score.isnot(None),
            ERDiagramQuestion.is_deleted == 0,
        )
        .count()
    )

    return ERDiagramQuestionCountResponse(total=total, attempted=attempted)


@router.get("/questions/{question_id}", response_model=ERDiagramQuestionResponse, response_model_exclude_none=True)
def get_er_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Tiny lookup that serves as the 404 check and the per-user authorization gate below
    # (creator role + is_published, small columns only — not the heavy problem statement /
    # rubric). The full serialized payload is cached per id.
    row = (
        db.query(ERDiagramQuestion.is_published, User.role)
        .join(User, ERDiagramQuestion.created_by == User.id)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )

    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    is_published, creator_role = row
    role_value = creator_role.value if isinstance(creator_role, UserRole) else str(creator_role).strip().lower()

    # Publish gate applies only to staff-created BANK ER questions. Student-created questions are
    # never gated. For a gated (unpublished, staff-created) question — which includes assessment
    # clones (is_published=0) — a student may load it only as an active participant in a running
    # assessment that contains it; a random ID-guesser is rejected. Mirrors labs.get_lab.
    if (
        current_user.role.value == "student"
        and role_value in {"staff", "admin"}
        and not is_published
    ):
        if not _er_question_accessible_via_assessment(question_id, current_user.id, db):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    # Staff always see the rubric (they author and edit it, and the edit screen
    # prefills from this response) plus the graded-attempt count. That payload is
    # role-specific, so it bypasses the per-id cache used for students.
    if current_user.role in {UserRole.STAFF, UserRole.ADMIN}:
        question = (
            db.query(ERDiagramQuestion)
            .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
            .first()
        )
        if not question:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
        return _to_response(
            question,
            hide_rubric_when_disabled=False,
            attempt_count=_count_graded_attempts(db, question_id),
        )

    # Student payload is identical for every student (rubric hidden unless the
    # author opted in), so cache per id. Invalidated on any question mutation.
    def producer():
        question = (
            db.query(ERDiagramQuestion)
            .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
            .first()
        )
        if not question:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
        return _to_response(question)

    return cache_read(db, Ns.ER_QUESTIONS, key=("detail", question_id), producer=producer)


def _set_er_published(question_id: int, published: int, db: Session) -> ERDiagramQuestion:
    """Shared helper for ER publish/unpublish: flip is_published, commit, return the question."""
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )

    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    question.is_published = published
    db.commit()
    db.refresh(question)
    return question


@router.post("/questions/{question_id}/publish", response_model=ERDiagramQuestionResponse, response_model_exclude_none=True)
def publish_er_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Publish an ER question (staff only). Sets is_published=1 so students can see it."""
    return _to_response(_set_er_published(question_id, 1, db))


@router.post("/questions/{question_id}/unpublish", response_model=ERDiagramQuestionResponse, response_model_exclude_none=True)
def unpublish_er_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Unpublish an ER question (staff only). Sets is_published=0 so students can no longer see it."""
    return _to_response(_set_er_published(question_id, 0, db))


async def _stream_with_erd_tutor_state(
    *,
    stream,
    db: Session,
    conversation,
    mode: str,
    student_query: Optional[str] = None,
    submission_description: Optional[str] = None,
    submission_context: Optional[dict] = None,
):
    """Wrap a LangGraph submit/query stream and, on the ``done`` event, persist
    the updated ERD-tutor conversation state + transcript messages.

    This is only used when ``ERD_TUTOR_ENGINE == "langgraph"``. It is a no-op
    overlay on the SSE bytes (every chunk is forwarded verbatim, exactly like
    ``stream_with_lab_persistence``); the persistence happens as a side effect
    after the terminal event is observed. The legacy Dify path never reaches
    here, so its behavior is unchanged.

    The wrapped source is async (LangGraph runners), but a sync source is also
    accepted defensively and pumped through the threadpool. The one-time
    persistence writes are offloaded with ``asyncio.to_thread`` so they never
    block the event loop.
    """
    from app.services.erd_tutor import persistence as erd_persistence

    source = stream if hasattr(stream, "__aiter__") else iterate_in_threadpool(stream)
    buffer = ""
    done_payload: Optional[dict[str, Any]] = None
    async for chunk in source:
        yield chunk
        buffer += chunk.decode("utf-8", "replace") if isinstance(chunk, (bytes, bytearray)) else chunk
        while "\n\n" in buffer:
            block, buffer = buffer.split("\n\n", 1)
            event_name: Optional[str] = None
            data_lines: list[str] = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
            if event_name == "done" and data_lines:
                try:
                    done_payload = json.loads("\n".join(data_lines))
                except (json.JSONDecodeError, ValueError):
                    done_payload = None

    if done_payload is None:
        # error / partial stream — leave conversation state untouched.
        return

    structured = done_payload.get("structured_output") or {}

    def _persist():
        if mode == "Query":
            upd = structured.get("state_update") or {}
            next_stage = upd.get("next_ibl_stage") or conversation.ibl_stage
            next_hint = upd.get("next_hint_level")
            if not isinstance(next_hint, int):
                next_hint = conversation.hint_level
            erd_persistence.save_state(
                db,
                conversation,
                ibl_stage=next_stage,
                hint_level=next_hint,
                misconceptions=upd.get("misconceptions") or [],
                last_student_goal=str(upd.get("last_student_goal") or ""),
                last_query_summary=str(upd.get("query_summary") or ""),
            )
            if student_query:
                erd_persistence.append_message(
                    db, conversation, role="user", mode="query", content=student_query,
                )
            erd_persistence.append_message(
                db,
                conversation,
                role="assistant",
                mode="query",
                content=str(done_payload.get("text") or ""),
            )
        else:
            ibl = structured.get("ibl") or {}
            next_stage = ibl.get("next_stage") or conversation.ibl_stage
            next_hint = ibl.get("next_hint_level")
            if not isinstance(next_hint, int):
                next_hint = conversation.hint_level
            save_fields = dict(
                ibl_stage=next_stage,
                hint_level=next_hint,
                last_submit_report=structured,
                last_submit_score=structured.get("score") or {},
            )
            # Keep the canonical ERD for the query tutor. Only overwrite when the
            # pipeline actually extracted something, so a failed parse doesn't
            # clobber the last good model.
            canonical = done_payload.get("canonical_erd") or {}
            if canonical.get("entities") or canonical.get("relationships"):
                save_fields["current_erd_model"] = canonical
            erd_persistence.save_state(db, conversation, **save_fields)
            # Analytics row is recorded before the transcript appends so a
            # transcript failure can never lose the graded attempt.
            if submission_context is not None:
                from app.models.er_submission import ErSubmission

                def _flt(v):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        return None

                score = structured.get("score") or {}
                checks = structured.get("checks")
                db.add(ErSubmission(
                    user_id=submission_context["user_id"],
                    er_diagram_question_id=submission_context["question_id"],
                    score_earned=_flt(score.get("earned_points")),
                    score_total=_flt(score.get("total_points")),
                    score_percent=_flt(score.get("percent")),
                    score_label=(str(score.get("label") or "").strip() or None),
                    checks_json=(json.dumps(checks, ensure_ascii=False)
                                 if isinstance(checks, list) else None),
                    submitted_image_storage_key=submission_context.get("image_key"),
                    submitted_xml=submission_context.get("xml_text"),
                    submission_description=submission_context.get("description"),
                    hint_level_at_submit=submission_context.get("hint_level"),
                    ibl_stage_at_submit=submission_context.get("ibl_stage"),
                ))
                db.commit()
            if (submission_description or "").strip():
                erd_persistence.append_message(
                    db,
                    conversation,
                    role="user",
                    mode="submit",
                    content=submission_description.strip(),
                )
            erd_persistence.append_message(
                db,
                conversation,
                role="submission",
                mode="submit",
                content=str(done_payload.get("text") or ""),
            )

    try:
        # Offload the blocking DB writes so they never block the event loop.
        await asyncio.to_thread(_persist)
    except Exception:  # never let persistence break the already-delivered stream
        logger.exception("erd_tutor: failed to persist conversation state after %s", mode)


def _erd_conversation_payload(db: Session, conversation) -> dict[str, Any]:
    """Serialize an ERD-tutor conversation + transcript for the GET endpoint."""
    from app.services.erd_tutor import persistence as erd_persistence

    def _json(s):
        try:
            return json.loads(s) if s else None
        except (json.JSONDecodeError, ValueError):
            return None

    return {
        "exists": True,
        "conversation_id": conversation.id,
        "context_type": conversation.context_type,
        "ibl_stage": conversation.ibl_stage,
        "hint_level": conversation.hint_level,
        "last_submit_score": _json(conversation.last_submit_score),
        "last_submit_report": _json(conversation.last_submit_report),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "mode": m.mode,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in erd_persistence.transcript(db, conversation)
        ],
    }


_EMPTY_CONVERSATION: dict[str, Any] = {
    "exists": False, "conversation_id": None, "context_type": None,
    "ibl_stage": None, "hint_level": None, "last_submit_score": None, "messages": [],
}


@router.get("/conversation")
def get_erd_tutor_conversation(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch the current user's ERD-tutor transcript for a question.

    Read-only — never creates a conversation. Returns ``exists: false`` with an
    empty transcript when there is nothing yet (including on the Dify engine,
    which records no conversations).
    """
    from app.services.erd_tutor import persistence as erd_persistence

    conv = erd_persistence.find_conversation(
        db, user_id=current_user.id, context_type="standalone",
        er_diagram_question_id=question_id,
    )

    if conv is None:
        return _EMPTY_CONVERSATION
    return _erd_conversation_payload(db, conv)


@router.post("/submission")
async def submit_er_diagram(
    question_id: Optional[int] = Form(None),
    mode: ERSubmissionMode = Form(...),
    student_query: Optional[str] = Form(None),
    submission_xml_text: Optional[str] = Form(None),
    submission_description: Optional[str] = Form(None),
    erd_img: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if question_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="question_id is required",
        )

    query_text = student_query.strip() if isinstance(student_query, str) else ""
    xml_text = submission_xml_text.strip() if isinstance(submission_xml_text, str) else ""
    if len(xml_text) > MAX_ER_XML_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"submission_xml_text exceeds maximum length of {MAX_ER_XML_CHARS} characters",
        )
    desc_text = submission_description.strip() if isinstance(submission_description, str) else ""
    if len(desc_text) > MAX_ER_DESC_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"submission_description exceeds maximum length of {MAX_ER_DESC_CHARS} characters",
        )
    if mode == "Query":
        if not query_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="student_query is required when mode is Query")
    else:
        if not xml_text and not erd_img:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Provide either submission_xml_text or erd_img when mode is Submit")
        # Both together is the preferred draw.io submission: the XML gives the
        # grader exact structure (it is what the PNG was rendered from), while
        # the image is what gets stored for analytics and shown to the tutor.
        # They were mutually exclusive when XML was an alternative input rather
        # than a companion to it.
        if erd_img and (not erd_img.content_type or not erd_img.content_type.startswith("image/")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="erd_img must be an image file")

    # LangGraph adds standalone tutor state; the Dify default is unchanged.
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    # LangGraph engine: per-user standalone conversation so submits feed the
    # query tutor (canonical ERD + last report) and stage/hint carry across turns.
    erd_conversation = None
    erd_ibl_stage, erd_hint_level = "orientation", 1
    erd_last_submit_report: Optional[dict] = None
    erd_current_erd_model: Optional[dict] = None
    if settings.ERD_TUTOR_ENGINE == "langgraph":
        from app.services.erd_tutor import persistence as erd_persistence

        erd_conversation = erd_persistence.get_or_create_conversation(
            db,
            user_id=current_user.id,
            context_type="standalone",
            er_diagram_question_id=question.id,
        )
        _loaded = erd_persistence.loaded_state(erd_conversation)
        erd_ibl_stage = _loaded["ibl_stage"]
        erd_hint_level = _loaded["hint_level"]
        erd_last_submit_report = _loaded["last_submit_report"]
        erd_current_erd_model = _loaded["current_erd_model"]

    # Persist the submitted diagram for staff analytics. Never blocks grading:
    # a storage failure just leaves the key null.
    submission_image_key: Optional[str] = None
    if (
        mode == "Submit"
        and erd_img is not None
        and settings.ERD_TUTOR_ENGINE == "langgraph"
    ):
        try:
            await erd_img.seek(0)
            provider = get_er_storage_provider()
            # Offloaded: provider.save is synchronous I/O (local disk, or a full
            # Azure blob upload) and must never block the event loop.
            submission_image_key, _ = await asyncio.to_thread(provider.save, erd_img)
        except Exception:
            logger.exception("er_submissions: image save failed; grading continues")
        finally:
            await erd_img.seek(0)

    if erd_conversation is not None and mode == "Query":
        from app.services.erd_tutor import runner as erd_runner

        image_bytes_q: Optional[bytes] = None
        if erd_img is not None and erd_img.filename:
            image_bytes_q = erd_img.file.read()
        stream = erd_runner.stream_er_query(
            question_id=question.id,
            problem_statement=question.problem_statement,
            difficulty_label=question.difficulty_label,
            rubric_json=question.rubric_json,
            student_query=query_text or "",
            image_bytes=image_bytes_q,
            ibl_stage=erd_ibl_stage,
            hint_level=erd_hint_level,
            current_erd_model=erd_current_erd_model,
            last_submit_report=erd_last_submit_report,
        )
    elif erd_conversation is not None:  # Submit on langgraph, with carried state
        stream = stream_er_submission_grading(
            question_id=question.id,
            problem_statement=question.problem_statement,
            difficulty_label=question.difficulty_label,
            rubric_json=question.rubric_json,
            submission_xml_text=xml_text or None,
            student_query=query_text or None,
            erd_img=erd_img,
            ibl_stage=erd_ibl_stage,
            hint_level=erd_hint_level,
            last_submit_report=erd_last_submit_report,
            submission_description=desc_text or None,
        )
    else:
        stream = _call_dify_er_submission(
            question=question,
            mode=mode,
            student_query=query_text or None,
            submission_xml_text=xml_text or None,
            erd_img=erd_img,
        )

    if erd_conversation is not None:
        stream = _stream_with_erd_tutor_state(
            stream=stream,
            db=db,
            conversation=erd_conversation,
            mode=mode,
            student_query=query_text or "",
            submission_description=desc_text or None,
            submission_context=(
                {
                    "user_id": current_user.id,
                    "question_id": question.id,
                    "image_key": submission_image_key,
                    "xml_text": (xml_text or None),
                    "description": (desc_text or None),
                    "hint_level": erd_hint_level,
                    "ibl_stage": erd_ibl_stage,
                }
                if mode == "Submit"
                else None
            ),
        )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.put("/questions/{question_id}", response_model=ERDiagramQuestionResponse)
def update_er_question(
    question_id: int,
    title: str = Form(...),
    problem_statement: str = Form(...),
    notation: str = Form("Chen"),
    difficulty_label: DifficultyLabel = Form(...),
    difficulty_rationale: str = Form(...),
    rubric_md: str = Form(...),
    rubric_json: str = Form("{}"),
    instruction_history: str = Form("[]"),
    show_rubric_on_attempt: bool = Form(False),
    model_answer: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    """Update a question-bank ERD question (staff only).

    Mirrors ``PUT /questions/{id}`` for SQL questions: same multipart shape as
    the create endpoint, staff-gated at the dependency. Omitting ``model_answer``
    keeps the stored image; supplying one replaces it.
    """
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    if not title.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title is required")
    if not problem_statement.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="problem_statement is required")
    if not rubric_md.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rubric_md is required")
    if not difficulty_rationale.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="difficulty_rationale is required")

    parsed_rubric = _parse_json_field(rubric_json, "rubric_json")
    if not isinstance(parsed_rubric, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rubric_json must be a JSON object")

    parsed_history = _parse_json_field(instruction_history, "instruction_history")
    if not isinstance(parsed_history, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="instruction_history must be a JSON array",
        )

    if model_answer is not None and model_answer.filename:
        provider = get_er_storage_provider()
        storage_key, _path = provider.save(model_answer)
        question.model_answer_storage_key = storage_key

    question.title = title.strip()
    question.problem_statement = problem_statement.strip()
    question.notation = notation
    question.difficulty_label = difficulty_label
    question.difficulty_rationale = difficulty_rationale.strip()
    question.rubric_md = rubric_md
    question.rubric_json = json.dumps(
        _with_rubric_visibility_meta(parsed_rubric, show_rubric_on_attempt)
    )
    question.instruction_history_json = json.dumps([str(i) for i in parsed_history])

    db.commit()
    db.refresh(question)

    return _to_response(
        question,
        hide_rubric_when_disabled=False,
        attempt_count=_count_graded_attempts(db, question.id),
    )


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_er_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )

    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    if current_user.role not in {UserRole.STAFF, UserRole.ADMIN} and question.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the question owner or staff can delete this question",
        )

    question.is_deleted = 1
    db.commit()

    return None
