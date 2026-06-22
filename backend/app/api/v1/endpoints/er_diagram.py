import json
import logging
import re
import time
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.user import User, UserRole
from app.schemas.er_diagram import (
    DifficultyLabel,
    ERDiagramQuestionResponse,
    ERDiagramQuestionListItem,
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
from app.utils.er_storage import get_er_storage_provider

router = APIRouter(prefix="/er-diagram", tags=["er-diagram"])
logger = logging.getLogger(__name__)
MAX_ER_XML_CHARS = 500_000
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


def _to_response(question: ERDiagramQuestion, *, hide_rubric_when_disabled: bool = True) -> ERDiagramQuestionResponse:
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
    )


@router.post("/rubric/generate", response_model=GenerateRubricResponse)
def generate_er_rubric(
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

    dify_payload = _call_dify_generate_rubric(
        mode=mode,
        notation=notation,
        problem_statement=statement,
        refinement_instruction=refinement,
        rubric_previous=rubric_previous,
        instruction_history=instruction_history,
        model_answer=model_answer,
    )

    return GenerateRubricResponse(**dify_payload)


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
    _: User = Depends(get_current_user),
):
    question_rows = (
        db.query(ERDiagramQuestion, User.role)
        .join(User, ERDiagramQuestion.created_by == User.id)
        .filter(ERDiagramQuestion.is_deleted == 0)
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

        items.append(
            ERDiagramQuestionListItem(
                id=question.id,
                title=question.title,
                problem_statement=question.problem_statement[:200].strip(),
                difficulty_label=question.difficulty_label,
                created_by=question.created_by,
                created_by_role=role_value,
                created_at=question.created_at,
            )
        )

    return items


@router.get("/questions/{question_id}", response_model=ERDiagramQuestionResponse, response_model_exclude_none=True)
def get_er_question(
    question_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )

    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    return _to_response(question)


@router.post("/submission")
def submit_er_diagram(
    question_id: Optional[int] = Form(None),
    mode: ERSubmissionMode = Form(...),
    student_query: Optional[str] = Form(None),
    submission_xml_text: Optional[str] = Form(None),
    erd_img: Optional[UploadFile] = File(None),
    er_lab_id: Optional[int] = Form(None),
    er_lab_question_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Exactly one of (question_id) vs (er_lab_id + er_lab_question_id) must be supplied.
    bank_mode = question_id is not None
    lab_mode = er_lab_id is not None and er_lab_question_id is not None
    if bank_mode == lab_mode:  # both true or both false
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Supply either question_id (bank) OR er_lab_id+er_lab_question_id (lab), not both.",
        )
    if er_lab_id is not None and er_lab_question_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="er_lab_question_id is required when er_lab_id is supplied")
    if er_lab_question_id is not None and er_lab_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="er_lab_id is required when er_lab_question_id is supplied")

    query_text = student_query.strip() if isinstance(student_query, str) else ""
    xml_text = submission_xml_text.strip() if isinstance(submission_xml_text, str) else ""
    if len(xml_text) > MAX_ER_XML_CHARS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"submission_xml_text exceeds maximum length of {MAX_ER_XML_CHARS} characters",
        )
    if mode == "Query":
        if not query_text:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="student_query is required when mode is Query")
    else:
        if not xml_text and not erd_img:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Provide either submission_xml_text or erd_img when mode is Submit")
        if xml_text and erd_img:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Provide only one submission input: submission_xml_text or erd_img")
        if erd_img and (not erd_img.content_type or not erd_img.content_type.startswith("image/")):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="erd_img must be an image file")

    # ----- Bank mode: unchanged from today -----
    if bank_mode:
        question = (
            db.query(ERDiagramQuestion)
            .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
            .first()
        )
        if not question:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
        stream = _call_dify_er_submission(
            question=question,
            mode=mode,
            student_query=query_text or None,
            submission_xml_text=xml_text or None,
            erd_img=erd_img,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ----- Lab mode -----
    from app.models.er_lab import ErLab
    from app.models.er_lab_question import ErLabQuestion
    from app.models.er_lab_session import ErLabSession
    from app.services.er_lab_submission_persistence import stream_with_lab_persistence
    from app.utils.er_storage import get_er_storage_provider
    from app.services.er_grading import stream_er_submission_grading, _wrap_bytes_as_upload_file

    lab = db.query(ErLab).filter(ErLab.id == er_lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab not found")

    is_staff = current_user.role.value in {"staff", "admin"}
    if not is_staff and lab.is_running == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Lab is not running")

    er_lab_question = db.query(ErLabQuestion).filter(
        ErLabQuestion.id == er_lab_question_id,
        ErLabQuestion.er_lab_id == er_lab_id,
        ErLabQuestion.is_deleted == 0,
    ).first()
    if not er_lab_question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lab question not found")

    session = db.query(ErLabSession).filter(
        ErLabSession.er_lab_id == er_lab_id,
        ErLabSession.user_id == current_user.id,
        ErLabSession.is_active == 1,
    ).first()
    if not session and not is_staff:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No active session for this lab")

    image_key: Optional[str] = None
    image_bytes: Optional[bytes] = None
    if mode == "Submit" and erd_img is not None and erd_img.filename:
        image_bytes = erd_img.file.read()
        provider = get_er_storage_provider()
        wrapped_for_save = _wrap_bytes_as_upload_file(image_bytes, filename=(erd_img.filename or "submission.png"))
        image_key, _path = provider.save(wrapped_for_save)

    if mode == "Submit":
        grading_stream = stream_er_submission_grading(
            question_id=er_lab_question.id,
            problem_statement=er_lab_question.problem_statement,
            difficulty_label=er_lab_question.difficulty_label,
            rubric_json=er_lab_question.rubric_json,
            submission_xml_text=xml_text or None,
            student_query=query_text or None,
            erd_img=None,
            image_bytes=image_bytes,
        )
    else:
        # Query mode in lab — reuse the existing er_diagram.py helper which handles both modes.
        # It only reads question.id, .problem_statement, .difficulty_label, .rubric_json
        # — all of which ErLabQuestion exposes with matching names.
        grading_stream = _call_dify_er_submission(
            question=er_lab_question,
            mode=mode,
            student_query=query_text or None,
            submission_xml_text=None,
            erd_img=None,
        )

    if mode == "Submit" and session is not None:
        wrapped_stream = stream_with_lab_persistence(
            stream=grading_stream,
            db=db,
            er_lab_id=er_lab_id,
            er_lab_question_id=er_lab_question_id,
            user_id=current_user.id,
            session_id=session.id,
            submitted_xml=xml_text or None,
            submitted_image_storage_key=image_key,
        )
    else:
        # Query mode (no persistence) or staff with no session (still no persistence)
        wrapped_stream = grading_stream

    return StreamingResponse(
        wrapped_stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
