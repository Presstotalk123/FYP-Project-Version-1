import asyncio
import contextlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session
from starlette.concurrency import iterate_in_threadpool

from app.config import settings
from app.database import get_db, SessionLocal
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
    ERDiagramQuestionProgressItem,
    ErDraftResponse,
    ErDraftSaveRequest,
    ErDraftSaveResponse,
    ErImageDraftResponse,
    ErImageDraftSaveResponse,
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
from app.services import er_drafts
from app.services import er_image_drafts
from app.services.erd_rubric import runner as erd_rubric_runner
from app.utils.er_storage import get_er_storage_provider

router = APIRouter(prefix="/er-diagram", tags=["er-diagram"])
logger = logging.getLogger(__name__)

# ── Detached grading producers ────────────────────────────────────────────
# A LangGraph Submit/Query grade runs to completion in a background producer
# task that is decoupled from the HTTP response (see _stream_with_erd_tutor_state).
# That is what lets a student refresh mid-grade without losing the graded attempt:
# the client's SSE connection dying cancels only the consumer, never the producer.
#
# asyncio keeps only a *weak* reference to tasks created with create_task, so a
# producer with no other live reference can be garbage-collected mid-grade. Hold a
# strong reference here for the task's lifetime and drop it in the done-callback.
_ERD_PRODUCER_TASKS: set[asyncio.Task] = set()

# In-flight Submit grades keyed on (user_id, question_id). Because a producer
# survives client disconnect, an anxious student who refreshes and *resubmits*
# would otherwise start a second concurrent LLM grade that races the first on
# last_submit_report and writes a duplicate ErSubmission row. While one is in
# flight we refuse to start another for the same (user, question).
_ERD_INFLIGHT_SUBMITS: set[tuple[int, int]] = set()

# ── Grade concurrency cap ─────────────────────────────────────────────────
# Each ER Submit grade is a single ~50k-token LLM call, and the model's ~500k
# tokens/min budget allows only ~10 at once. This semaphore caps concurrent
# grades so a mass end-of-assessment finalize (or the staff bulk sweep) can't
# flood the model. It is PER WORKER: an asyncio.Semaphore is bound to one event
# loop, so with N gunicorn workers the deployment total is
# ERD_GRADE_MAX_CONCURRENCY × N — hence the default (5) is the global budget (10)
# divided by the expected worker count (2). See config.py's note. Created lazily
# so it binds to the running loop rather than import time.
_ERD_GRADE_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _erd_grade_semaphore() -> asyncio.Semaphore:
    global _ERD_GRADE_SEMAPHORE
    if _ERD_GRADE_SEMAPHORE is None:
        _ERD_GRADE_SEMAPHORE = asyncio.Semaphore(settings.ERD_GRADE_MAX_CONCURRENCY)
    return _ERD_GRADE_SEMAPHORE

# Sentinel pushed onto the producer→consumer queue to mark end-of-stream.
_ERD_QUEUE_DONE = object()


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
            # "Live" = is_running (classic) OR gateway_enabled (window-driven, is_running=0).
            ((Assessment.is_running == 1) | (Assessment.gateway_enabled == 1)),
            AssessmentItem.item_id == question_id,
            AssessmentItem.item_type == "er_question",
        )
        .first()
    )
    return result is not None


def _require_er_question_access(db: Session, *, question_id: int, current_user: User) -> None:
    """Authorization gate for the draft endpoints — raises 404 exactly where
    `get_er_question` (~line 1215) would refuse to serve the question itself.

    Selects only (is_published, creator role), not the full question row: this
    doubles as the existence check on the hot autosave write path, so callers
    should not do a second, heavier lookup afterward.

    The publish gate applies only to staff-created bank questions; student-
    authored questions are never gated (mirrors get_er_question). A student
    reaches a gated (unpublished, staff-created) question — which includes
    assessment clones, whose is_published is 0 by construction — only as an
    active participant in a running assessment containing it. Staff/admin are
    never gated.
    """
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

    if (
        current_user.role.value == "student"
        and role_value in {"staff", "admin"}
        and not is_published
    ):
        if not _er_question_accessible_via_assessment(question_id, current_user.id, db):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")


# Sourced from settings so a deployment can raise it without a code change; see
# the note on ER_MAX_XML_CHARS in config.py about keeping the client in step.
# Read once at import, matching how the rest of this module treats settings.
MAX_ER_XML_CHARS = settings.ER_MAX_XML_CHARS
MAX_ER_IMAGE_BYTES = settings.ER_MAX_IMAGE_BYTES
MAX_ER_DESC_CHARS = 5_000


def _validate_erd_image_upload(upload: UploadFile) -> None:
    """Reject a non-image upload with the same 400 the submission endpoint uses.
    Shared by /submission and the image-draft PUT so both refuse identically."""
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="erd_img must be an image file",
        )


def _resolve_er_storage_path(storage_key: str) -> Path:
    """Resolve a storage key to a local file path, guarding against traversal.

    Local-provider only, matching get_er_model_answer / get_submission_image —
    Azure serving is deferred across the ER feature. Raises 404 when the key
    looks tampered (path separators) or the file is missing from storage.
    """
    if not storage_key or "/" in storage_key or "\\" in storage_key or ".." in storage_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Image missing from storage")
    path = Path(settings.ER_DIAGRAM_UPLOAD_PATH) / storage_key
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Image missing from storage")
    return path
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


@router.get("/progress", response_model=list[ERDiagramQuestionProgressItem])
def get_er_question_progress(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Per-question standalone progress for the current user's question list.

    The same signal `/questions/count` aggregates, itemised: one row per question
    with a graded standalone submission. Untouched questions are simply absent.

    `completed` reads the grader's own verdict out of the `last_submit_score` JSON
    rather than thresholding `percent`, so a question counts as done exactly when
    the student was told it passed. A row whose JSON is unreadable degrades to
    attempted-but-not-completed — a list badge is not worth a 500.
    """
    rows = (
        db.query(
            ErdTutorConversation.er_diagram_question_id,
            ErdTutorConversation.last_submit_score,
        )
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
        .all()
    )

    progress: list[ERDiagramQuestionProgressItem] = []
    for question_id, raw_score in rows:
        completed = False
        try:
            data = json.loads(raw_score)
            completed = isinstance(data, dict) and data.get("label") == "pass"
        except (TypeError, ValueError):
            logger.warning(
                "Unreadable last_submit_score for user %s question %s",
                current_user.id,
                question_id,
            )
        progress.append(
            ERDiagramQuestionProgressItem(question_id=question_id, completed=completed)
        )
    return progress


@router.get("/questions/{question_id}/model-answer")
def get_er_model_answer(
    question_id: int,
    db: Session = Depends(get_db),
    _staff: User = Depends(require_staff_role),
):
    """The author's model answer image, so the edit screen can show the diagram the
    rubric was generated from instead of a filename.

    Staff only, and deliberately so: this is the answer key. The edit page is
    already staff-gated, and no student-facing screen has a reason to fetch it.

    model_answer_url is a filesystem path, not a URL — it is stored with the OS
    separator and cannot be served — so the stored key is resolved against the
    upload directory the same way the attempt-image endpoint does.
    """
    row = (
        db.query(ERDiagramQuestion.model_answer_storage_key)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    key = row[0]
    if not key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No model answer stored for this question")
    # Keys are server-generated UUID filenames; anything with a path separator is
    # not ours. Belt-and-braces against traversal via a tampered row.
    if "/" in key or "\\" in key or ".." in key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Model answer missing from storage")
    path = Path(settings.ER_DIAGRAM_UPLOAD_PATH) / key
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Model answer missing from storage")
    return FileResponse(path)


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


async def _credit_after_stream(inner, db: Session, session, query_start):
    """Yield the wrapped stream verbatim, then credit the elapsed grading time to end_time.

    The engine-agnostic outer wrapper for the assessment timer: it layers over both the langgraph
    ``_stream_with_erd_tutor_state`` wrapper and the raw Dify stream, so an in-assessment ER Submit
    credits its grading latency regardless of ``ERD_TUTOR_ENGINE`` — mirroring ``credit_query_time``
    on the SQL Run path. Crediting runs after the inner stream is exhausted and before this generator
    returns, so the HTTP response closes only once the pushed-forward ``end_time`` is committed; the
    client's stream-close is therefore a safe signal that a ``getSession`` re-fetch will read the
    credited deadline. Accepts a sync or async source (matches ``_stream_with_erd_tutor_state``).
    """
    from app.services.assessment_timer import credit_query_time

    source = inner if hasattr(inner, "__aiter__") else iterate_in_threadpool(inner)
    async for chunk in source:
        yield chunk
    # Offload the blocking DB write so it never blocks the event loop.
    await asyncio.to_thread(credit_query_time, db, session, query_start)


def _persist_erd_state_fresh_session(
    *,
    conversation_id: int,
    mode: str,
    done_payload: Optional[dict[str, Any]],
    student_query: Optional[str],
    submission_description: Optional[str],
    submission_context: Optional[dict],
    credit: Optional[tuple[int, Any]],
) -> None:
    """Persist ERD-tutor state (+ optional assessment-timer credit) on a FRESH DB
    session, re-fetching the conversation by id.

    Runs in a threadpool (blocking SQLAlchemy) from the detached grading producer,
    which may outlive the HTTP request — so it must NOT use the request-scoped
    session (torn down when the request ends) and instead opens its own. The session
    is opened here, at persist time, and closed immediately: it is never held across
    the 30-90s grade, so it borrows a pooled connection only for these brief writes.

    ``done_payload`` may be None (a grading error): conversation state is then left
    untouched, but any assessment-timer credit is still applied — matching the
    pre-refactor ``_credit_after_stream``, which credited the elapsed time back even
    on a failed grade so a student is never charged for grading latency.
    """
    from app.services.erd_tutor import persistence as erd_persistence
    from app.models.erd_tutor_conversation import ErdTutorConversation

    db = SessionLocal()
    try:
        if done_payload is not None:
            conversation = (
                db.query(ErdTutorConversation)
                .filter(ErdTutorConversation.id == conversation_id)
                .first()
            )
            if conversation is None:
                logger.warning(
                    "erd_tutor: conversation %s missing at persist time", conversation_id
                )
            else:
                structured = done_payload.get("structured_output") or {}
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
                    # Keep the canonical ERD for the query tutor. Only overwrite when
                    # the pipeline actually extracted something, so a failed parse
                    # doesn't clobber the last good model.
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

        # Credit the assessment clock on this same fresh session, regardless of
        # whether the client is still connected (a mid-grade refresh must not cost
        # the student their grading time) and regardless of grading success.
        if credit is not None:
            from app.services.assessment_timer import credit_query_time
            from app.models.assessment_session import AssessmentSession

            session_id, query_start = credit
            sess = (
                db.query(AssessmentSession)
                .filter(AssessmentSession.id == session_id)
                .first()
            )
            credit_query_time(db, sess, query_start)
    finally:
        db.close()


async def _erd_grading_producer(
    *,
    source,
    queue: "asyncio.Queue",
    conversation_id: int,
    mode: str,
    student_query: Optional[str],
    submission_description: Optional[str],
    submission_context: Optional[dict],
    credit: Optional[tuple[int, Any]],
) -> None:
    """Consume the LangGraph SSE ``source`` to completion, forwarding every chunk onto
    ``queue`` for the HTTP consumer, then persist state + credit the timer.

    Runs as a detached task, so a client disconnect (which cancels the consumer) does
    NOT stop it — the grade still finishes and is saved. That is the whole point of
    the refactor. Persistence runs *before* the end-of-stream sentinel so that, for a
    client still connected, the SSE stream closes only once the graded result and the
    pushed-forward deadline are committed (the frontend treats stream-close as the cue
    to re-read the credited timer). The queue is unbounded, so forwarding never blocks
    even when nobody is reading (a departed client).
    """
    buffer = ""
    done_payload: Optional[dict[str, Any]] = None
    # Cap concurrent Submit grades (each ~50k tokens) against the LLM's token/min
    # budget — this is the same per-worker semaphore the batch finalize/bulk paths
    # use, so a student's Submit shares one budget with a mass sweep. Query turns
    # are cheap tutoring chat, so they stay ungated (nullcontext). The slot is held
    # only while tokens stream; persistence in the finally runs *outside* it so a
    # slot frees the instant the grade completes.
    grade_slot = _erd_grade_semaphore() if mode == "Submit" else contextlib.nullcontext()
    try:
        async with grade_slot:
            aiter_source = source if hasattr(source, "__aiter__") else iterate_in_threadpool(source)
            async for chunk in aiter_source:
                await queue.put(chunk)
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
    except Exception:
        logger.exception("erd_tutor: grading stream failed for conversation %s", conversation_id)
    finally:
        # Persist (and credit) before signalling end-of-stream, then always release
        # the consumer — even if persistence raised — so the client's stream closes.
        if done_payload is not None or credit is not None:
            try:
                await asyncio.to_thread(
                    _persist_erd_state_fresh_session,
                    conversation_id=conversation_id,
                    mode=mode,
                    done_payload=done_payload,
                    student_query=student_query,
                    submission_description=submission_description,
                    submission_context=submission_context,
                    credit=credit,
                )
            except Exception:  # never let persistence wedge the stream close
                logger.exception(
                    "erd_tutor: failed to persist conversation state after %s", mode
                )
        await queue.put(_ERD_QUEUE_DONE)


async def _erd_consume_queue(queue: "asyncio.Queue"):
    """Yield SSE chunks the producer puts on ``queue`` until the sentinel. On client
    disconnect this generator is cancelled and stops; the producer keeps running and
    persists the grade regardless."""
    while True:
        item = await queue.get()
        if item is _ERD_QUEUE_DONE:
            return
        yield item


async def _erd_already_grading_stream(mode: str, question_id: int):
    """Tiny SSE stream returned when a grade for this (user, question) is already in
    flight — we refuse to start a second concurrent grade and tell the student to
    wait (their first grade is still running detached and will be saved)."""
    yield _sse_event("start", {"mode": mode, "question_id": question_id})
    yield _sse_event(
        "error",
        {
            "detail": (
                "A grade for this question is already being computed. Please wait a "
                "moment, then reload the page to see your result."
            )
        },
    )


def _stream_with_erd_tutor_state(
    *,
    stream,
    conversation_id: int,
    mode: str,
    student_query: Optional[str] = None,
    submission_description: Optional[str] = None,
    submission_context: Optional[dict] = None,
    credit: Optional[tuple[int, Any]] = None,
    inflight_key: Optional[tuple[int, int]] = None,
):
    """Decouple a LangGraph submit/query grade from the HTTP response.

    Spawns a detached producer task (``_erd_grading_producer``) that runs the grade to
    completion and persists it on its own DB session, and returns a consumer async
    generator that forwards the producer's SSE chunks to the client. Because producer
    and consumer are separate tasks joined only by a queue, a client refresh cancels
    the consumer but never the producer — so the graded attempt is saved either way.

    Only used on ``ERD_TUTOR_ENGINE == "langgraph"``; the legacy Dify path never
    reaches here. Spawns eagerly (it is called from the async endpoint, where a loop is
    already running) so grading starts immediately and the in-flight guard is
    registered synchronously, before any second submit can race it.
    """
    queue: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(
        _erd_grading_producer(
            source=stream,
            queue=queue,
            conversation_id=conversation_id,
            mode=mode,
            student_query=student_query,
            submission_description=submission_description,
            submission_context=submission_context,
            credit=credit,
        )
    )
    # Strong ref (asyncio only weakly references tasks) + in-flight registration,
    # both dropped in the done-callback when the producer finishes.
    _ERD_PRODUCER_TASKS.add(task)
    if inflight_key is not None:
        _ERD_INFLIGHT_SUBMITS.add(inflight_key)

    def _cleanup(finished: asyncio.Task, key=inflight_key) -> None:
        _ERD_PRODUCER_TASKS.discard(finished)
        if key is not None:
            _ERD_INFLIGHT_SUBMITS.discard(key)

    task.add_done_callback(_cleanup)
    return _erd_consume_queue(queue)


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


@router.get("/draft", response_model=ErDraftResponse)
def get_er_draft(
    question_id: int,
    known_revision: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch the caller's in-progress canvas for a question.

    Always scoped to the caller — a user_id is never accepted from the client.
    Pass `known_revision` to skip the XML when the client is already current.
    """
    _require_er_question_access(db, question_id=question_id, current_user=current_user)

    if known_revision is not None:
        # Revision-only lookup first: the common "reopening a question I already
        # have" case must not pull the (up to 500 KB) xml column just to discard
        # it once the comparison below finds nothing changed.
        current = er_drafts.get_draft_revision(
            db, user_id=current_user.id, question_id=question_id
        )
        if current is None:
            return ErDraftResponse(exists=False)
        revision, updated_at = current
        if known_revision == revision:
            return ErDraftResponse(
                exists=True,
                revision=revision,
                updated_at=updated_at,
                unchanged=True,
            )
        # known_revision is stale — fall through to fetch the real content below.

    draft = er_drafts.get_draft(db, user_id=current_user.id, question_id=question_id)
    if draft is None:
        return ErDraftResponse(exists=False)

    return ErDraftResponse(
        exists=True,
        revision=draft.revision,
        updated_at=draft.updated_at,
        xml=draft.xml,
    )


@router.put("/draft", response_model=ErDraftSaveResponse)
def save_er_draft(
    payload: ErDraftSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upsert the caller's canvas. Never echoes the XML back."""
    if len(payload.xml) > MAX_ER_XML_CHARS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"xml exceeds maximum length of {MAX_ER_XML_CHARS} characters",
        )

    # Existence + authorization in one light query (not the full ORM row — this
    # runs on every autosave). See _require_er_question_access.
    _require_er_question_access(db, question_id=payload.question_id, current_user=current_user)

    revision, updated_at = er_drafts.save_draft(
        db,
        user_id=current_user.id,
        question_id=payload.question_id,
        xml=payload.xml,
    )
    return ErDraftSaveResponse(revision=revision, updated_at=updated_at)


@router.put("/image-draft", response_model=ErImageDraftSaveResponse)
async def save_er_image_draft(
    question_id: int = Form(...),
    erd_img: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upsert the caller's autosaved *uploaded-image* answer for a question.

    The image sibling of ``PUT /draft``: the workspace calls this the moment a
    student drops an image, so switching items or exiting never loses it. Stores
    the bytes via the ER storage provider and keeps only the key + metadata,
    then deletes the blob this replaced so no orphans accumulate.
    """
    _validate_erd_image_upload(erd_img)

    # Enforce the size cap by reading the body once (UploadFile.size isn't
    # reliably populated by every ASGI server), before the storage save so an
    # oversized upload never reaches disk/blob.
    await erd_img.seek(0)
    data = await erd_img.read()
    if len(data) > MAX_ER_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"image exceeds maximum size of {MAX_ER_IMAGE_BYTES} bytes",
        )
    await erd_img.seek(0)

    _require_er_question_access(db, question_id=question_id, current_user=current_user)

    provider = get_er_storage_provider()
    # Offloaded: provider.save is synchronous I/O (local disk, or a full Azure
    # blob upload) and must never block the event loop. Mirrors submit_er_diagram.
    storage_key, _ = await asyncio.to_thread(provider.save, erd_img)

    revision, updated_at, superseded_key = er_image_drafts.save_image_draft(
        db,
        user_id=current_user.id,
        question_id=question_id,
        storage_key=storage_key,
        filename=erd_img.filename,
        content_type=erd_img.content_type,
    )
    if superseded_key:
        try:
            await asyncio.to_thread(provider.delete, superseded_key)
        except Exception:
            logger.exception("image-draft: failed to delete superseded blob %s", superseded_key)

    return ErImageDraftSaveResponse(revision=revision, updated_at=updated_at)


@router.get("/image-draft", response_model=ErImageDraftResponse)
def get_er_image_draft(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Metadata for the caller's autosaved image answer (never the bytes).

    The client reads its IndexedDB cache first and calls this to learn the
    server's ``revision``; it fetches the bytes from ``/image-draft/content``
    only when the cache is missing or older than that revision.
    """
    _require_er_question_access(db, question_id=question_id, current_user=current_user)
    draft = er_image_drafts.get_image_draft(
        db, user_id=current_user.id, question_id=question_id
    )
    if draft is None:
        return ErImageDraftResponse(exists=False)
    return ErImageDraftResponse(
        exists=True,
        revision=draft.revision,
        updated_at=draft.updated_at,
        filename=draft.filename,
        content_type=draft.content_type,
    )


@router.get("/image-draft/content")
def get_er_image_draft_content(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The bytes of the caller's autosaved image answer, so a device with a cold
    IndexedDB cache (a different browser, or after browser eviction) can restore
    the dropzone preview. Local-provider serving, matching get_er_model_answer /
    get_submission_image; Azure serving is deferred across the ER feature.
    """
    _require_er_question_access(db, question_id=question_id, current_user=current_user)
    draft = er_image_drafts.get_image_draft(
        db, user_id=current_user.id, question_id=question_id
    )
    if draft is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No image draft stored for this question")
    path = _resolve_er_storage_path(draft.storage_key)
    return FileResponse(
        path,
        media_type=draft.content_type or "application/octet-stream",
        filename=draft.filename or None,
    )


@router.delete("/image-draft", status_code=status.HTTP_204_NO_CONTENT)
async def delete_er_image_draft(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove the caller's autosaved image answer — the student cleared the
    dropzone. Deletes the row and its blob so a subsequent finalize grades
    nothing for it."""
    _require_er_question_access(db, question_id=question_id, current_user=current_user)
    storage_key = er_image_drafts.delete_image_draft(
        db, user_id=current_user.id, question_id=question_id
    )
    if storage_key:
        try:
            provider = get_er_storage_provider()
            await asyncio.to_thread(provider.delete, storage_key)
        except Exception:
            logger.exception("image-draft: failed to delete blob %s on remove", storage_key)


@router.post("/submission")
async def submit_er_diagram(
    request: Request,
    question_id: Optional[int] = Form(None),
    mode: Optional[str] = Form(None),
    student_query: Optional[str] = Form(None),
    submission_xml_text: Optional[str] = Form(None),
    submission_description: Optional[str] = Form(None),
    erd_img: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Malformed-upload guard + diagnostics ──────────────────────────────
    # This endpoint's one required field is `mode`. When it is missing the
    # multipart body FastAPI received was empty, truncated, or not the form the
    # browser builds — the raw "mode: field required" 422 some students hit on
    # image submit while draw.io (an identical request shape) still works. The
    # cause sits on the client's device — an in-app/embedded browser, a
    # content-inspecting proxy / AV / MDM filter, or a page-rewriting extension
    # reshaping the upload — so it cannot be fixed server-side. What we can do is
    # stop failing opaquely: return an actionable message, and log the client and
    # exactly which parts did arrive so the next occurrence is self-diagnosing
    # from our own logs (no browser DevTools or Azure diagnostics needed).
    normalized_mode = (mode or "").strip()
    if normalized_mode not in ("Query", "Submit"):
        logger.warning(
            "er_submission_malformed_body user_id=%s question_id=%s mode=%r "
            "content_type=%r content_length=%s user_agent=%r via=%r xff=%r "
            "fields_present=%s erd_img=%s",
            getattr(current_user, "id", None),
            question_id,
            mode,
            request.headers.get("content-type"),
            request.headers.get("content-length"),
            request.headers.get("user-agent"),
            request.headers.get("via"),
            request.headers.get("x-forwarded-for"),
            {
                "question_id": question_id is not None,
                "student_query": bool((student_query or "").strip()),
                "submission_xml_text": bool((submission_xml_text or "").strip()),
                "submission_description": bool((submission_description or "").strip()),
                "erd_img": erd_img is not None and bool(getattr(erd_img, "filename", "")),
            },
            None if erd_img is None else {
                "filename": getattr(erd_img, "filename", None),
                "content_type": getattr(erd_img, "content_type", None),
                "size": getattr(erd_img, "size", None),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "We couldn't read your submission \u2014 the upload didn't arrive "
                "complete. This is usually caused by your browser, a browser extension, "
                "or a network/security filter on your device, not by your diagram. "
                "Please try submitting with the draw.io editor instead, or use a "
                "different browser or an incognito/private window. If it keeps "
                "happening, let your instructor know."
            ),
        )
    # Past the guard `mode` is exactly "Query" or "Submit"; canonicalise so the
    # downstream exact-match comparisons (e.g. the analytics image save) are safe.
    mode = normalized_mode

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
        if erd_img:
            _validate_erd_image_upload(erd_img)

    # LangGraph adds standalone tutor state; the Dify default is unchanged.
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    # Timing enforcement: if this ER question is being answered inside an assessment,
    # reject (and force-submit) once the student's deadline — personal timer or the
    # Timing-Gateway class-group window — has passed. Without this, ER items were the one
    # submit path that bypassed the assessment timer (execute.py / labs.py already enforce).
    from app.services.assessment_timer import enforce_not_expired
    _assessment_session = (
        db.query(AssessmentSession)
        .join(AssessmentItem, AssessmentItem.assessment_id == AssessmentSession.assessment_id)
        .filter(
            AssessmentSession.user_id == current_user.id,
            AssessmentSession.is_active == 1,
            AssessmentItem.item_id == question_id,
            AssessmentItem.item_type == "er_question",
        )
        .first()
    )
    enforce_not_expired(db, _assessment_session)  # 403 + finalize if past effective deadline

    # Grading credit: like a SQL Run, freeze the student's clock while the grade is computed and
    # push end_time forward by the elapsed time afterwards (see credit_after_stream below), so the
    # grading latency isn't charged against their assessment time. Only for an in-assessment Submit
    # (the tutor Query chat is deliberately not credited). enforce_not_expired above runs first, so
    # a request that arrives past the deadline is 403'd here and never reaches crediting. Start the
    # clock at request arrival (received_at middleware) so threadpool queueing time is credited too.
    from datetime import datetime, timezone
    credit_query_start = None
    if _assessment_session is not None and mode == "Submit":
        credit_query_start = getattr(request.state, "received_at", None) or datetime.now(timezone.utc)

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
        # Capture every id the detached producer needs BEFORE committing: a commit
        # expires these ORM objects, so touching an attribute afterwards would fire a
        # refresh SELECT that re-checks-out a pooled connection and pins it for the
        # rest of the request — exactly the connection-hold we are avoiding.
        conversation_id = erd_conversation.id
        assessment_session_id = _assessment_session.id if _assessment_session is not None else None
        submitter_id = current_user.id
        question_pk = question.id

        # Release the request session's pooled connection before the 30-90s grade so
        # it returns to the pool. get_or_create_conversation only commits when it
        # *creates*; on the resubmit path it returns a bare SELECT with an open
        # transaction that would otherwise pin one of the ~10 pooled connections for
        # the entire grade. The producer persists on its own fresh session; this
        # request touches the DB no further.
        db.commit()

        # De-dup: because the producer survives client disconnect, a student who
        # refreshes and resubmits must not kick off a second concurrent grade for the
        # same question. Checked here and registered synchronously inside the wrapper,
        # so two near-simultaneous submits cannot both slip through.
        inflight_key = (submitter_id, question_pk) if mode == "Submit" else None
        if inflight_key is not None and inflight_key in _ERD_INFLIGHT_SUBMITS:
            return StreamingResponse(
                _erd_already_grading_stream(mode, question_pk),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # Fold the assessment-timer credit into the producer's fresh session so a
        # mid-grade refresh still credits the elapsed grading time. (The old
        # _credit_after_stream outer wrapper ran only while the client stayed
        # connected, so a refresh dropped the credit along with the grade.)
        credit = (
            (assessment_session_id, credit_query_start)
            if credit_query_start is not None and assessment_session_id is not None
            else None
        )

        stream = _stream_with_erd_tutor_state(
            stream=stream,
            conversation_id=conversation_id,
            mode=mode,
            student_query=query_text or "",
            submission_description=desc_text or None,
            submission_context=(
                {
                    "user_id": submitter_id,
                    "question_id": question_pk,
                    "image_key": submission_image_key,
                    "xml_text": (xml_text or None),
                    "description": (desc_text or None),
                    "hint_level": erd_hint_level,
                    "ibl_stage": erd_ibl_stage,
                }
                if mode == "Submit"
                else None
            ),
            credit=credit,
            inflight_key=inflight_key,
        )
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Legacy Dify path (ERD_TUTOR_ENGINE != "langgraph"): unchanged. The credit is
    # applied by the outer _credit_after_stream wrapper, which drains the sync Dify
    # stream and credits afterwards. No conversation persistence exists on this path.
    if credit_query_start is not None:
        stream = _credit_after_stream(stream, db, _assessment_session, credit_query_start)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _drain_erd_stream_for_done(source) -> Optional[dict[str, Any]]:
    """Consume an ERD grading SSE ``source`` to completion and return the parsed
    ``done`` payload (or None on a grading error / no done event).

    The batch-finalize path grades to completion server-side without forwarding to
    a client, so unlike ``_erd_grading_producer`` there is no consumer queue — this
    just drains and extracts the result. The SSE block-parsing mirrors the producer.
    """
    buffer = ""
    done_payload: Optional[dict[str, Any]] = None
    aiter_source = source if hasattr(source, "__aiter__") else iterate_in_threadpool(source)
    async for chunk in aiter_source:
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
    return done_payload


async def _grade_pending_erd_question(
    *,
    db: Session,
    user_id: int,
    question_id: int,
    image_bytes: Optional[bytes],
    image_key: Optional[str],
) -> bool:
    """Grade one ER question's pending work as an end-of-assessment capture, reusing the
    normal Submit grading + persistence. Returns True when a grade actually ran, False when
    the pair was skipped (wrong engine, in-flight, no/empty/unchanged draft, missing question).

    Grades the student's *staged uploaded image* when ``image_bytes`` is supplied,
    otherwise the server-stored XML draft — and only when that draft changed since the
    last graded submission (``draft.updated_at`` newer than the latest ``ErSubmission``),
    so an unchanged diagram is never re-graded. LangGraph only: assessment ER scoring
    (``er_percent``) reads the conversation's ``last_submit_score``, which the Dify path
    never writes, so there is nothing to capture there.

    Connection discipline mirrors ``submit_er_diagram``: all ORM reads happen before the
    ``db.commit()`` that releases the pooled connection, so the 30-90s grade holds none;
    persistence runs on its own fresh session (``_persist_erd_state_fresh_session``).
    """
    if settings.ERD_TUTOR_ENGINE != "langgraph":
        return False
    # A concurrent grade for this (user, question) is already running detached; it will
    # persist on its own, so starting a second would only race it and duplicate a row.
    if (user_id, question_id) in _ERD_INFLIGHT_SUBMITS:
        return False

    from app.models.er_submission import ErSubmission
    from app.services.erd_tutor import persistence as erd_persistence

    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )
    if question is None:
        return False

    xml_text: Optional[str] = None
    if image_bytes is None:
        # Drawn answer: grade the flushed XML draft, but only if it changed since the
        # student's last explicit Submit.
        draft = er_drafts.get_draft(db, user_id=user_id, question_id=question_id)
        if draft is None or not (draft.xml or "").strip():
            return False
        last = (
            db.query(ErSubmission)
            .filter(
                ErSubmission.user_id == user_id,
                ErSubmission.er_diagram_question_id == question_id,
            )
            .order_by(ErSubmission.created_at.desc())
            .first()
        )
        if (
            last is not None
            and last.created_at is not None
            and draft.updated_at is not None
            and draft.updated_at <= last.created_at
        ):
            return False  # unchanged since last graded submission — skip
        xml_text = draft.xml

    # Capture every field the grade needs BEFORE the commit: a commit expires these ORM
    # objects, so a later attribute access would fire a refresh SELECT that re-checks-out
    # a pooled connection and pins it for the whole grade (the hold we are avoiding).
    q_problem = question.problem_statement
    q_difficulty = question.difficulty_label
    q_rubric = question.rubric_json

    conversation = erd_persistence.get_or_create_conversation(
        db, user_id=user_id, context_type="standalone", er_diagram_question_id=question_id,
    )
    loaded = erd_persistence.loaded_state(conversation)
    conversation_id = conversation.id
    ibl_stage = loaded["ibl_stage"]
    hint_level = loaded["hint_level"]
    last_submit_report = loaded["last_submit_report"]

    # Release the request session's pooled connection before the grade (get_or_create
    # leaves an open transaction on the resubmit path). The producer/persistence use a
    # fresh session; this request touches the DB no further until crediting.
    db.commit()

    stream = stream_er_submission_grading(
        question_id=question_id,
        problem_statement=q_problem,
        difficulty_label=q_difficulty,
        rubric_json=q_rubric,
        submission_xml_text=(xml_text or None),
        erd_img=None,
        image_bytes=image_bytes,
        ibl_stage=ibl_stage,
        hint_level=hint_level,
        last_submit_report=last_submit_report,
        submission_description=None,
    )

    _ERD_INFLIGHT_SUBMITS.add((user_id, question_id))
    try:
        done_payload = await _drain_erd_stream_for_done(stream)
        await asyncio.to_thread(
            _persist_erd_state_fresh_session,
            conversation_id=conversation_id,
            mode="Submit",
            done_payload=done_payload,
            student_query="",
            submission_description=None,
            submission_context={
                "user_id": user_id,
                "question_id": question_id,
                "image_key": image_key,
                "xml_text": (xml_text or None),
                "description": None,
                "hint_level": hint_level,
                "ibl_stage": ibl_stage,
            },
            credit=None,  # the batch credits elapsed time once, in the endpoint
        )
    finally:
        _ERD_INFLIGHT_SUBMITS.discard((user_id, question_id))
    return True


def _latest_submission_at(db: Session, *, user_id: int, question_id: int):
    """``created_at`` of the student's most recent graded submission for a
    question, or None. Snapshot this BEFORE grading anything this pass so the
    image-draft skip compares against submissions that predate it — grading the
    XML draft first can insert a fresh row that would otherwise wrongly suppress
    a genuine image draft."""
    from app.models.er_submission import ErSubmission

    row = (
        db.query(ErSubmission.created_at)
        .filter(
            ErSubmission.user_id == user_id,
            ErSubmission.er_diagram_question_id == question_id,
        )
        .order_by(ErSubmission.created_at.desc())
        .first()
    )
    return row[0] if row else None


async def _grade_pending_image_draft(
    *,
    db: Session,
    user_id: int,
    question_id: int,
    pre_grade_last_sub_at,
) -> bool:
    """Grade a student's persisted image draft as an attempt, skipping one that is
    unchanged since their last graded submission (the "no double-grade" guard,
    mirroring the XML skip). Returns True when a grade actually ran.

    Shared by the student's own finalize sweep and the staff bulk/refresh path so
    an uploaded-image answer is captured identically no matter who triggers the
    grade. Local-provider read only (Azure serving is deferred across the ER
    feature); a missing blob just skips. The submission reuses the draft's
    storage_key — these paths are terminal for the draft, so the shared blob is
    safe.
    """
    img_draft = er_image_drafts.get_image_draft(
        db, user_id=user_id, question_id=question_id
    )
    if img_draft is None:
        return False
    if (
        pre_grade_last_sub_at is not None
        and img_draft.updated_at is not None
        and img_draft.updated_at <= pre_grade_last_sub_at
    ):
        return False  # unchanged since last graded submission — skip
    try:
        draft_path = _resolve_er_storage_path(img_draft.storage_key)
        img_bytes = await asyncio.to_thread(draft_path.read_bytes)
    except HTTPException:
        return False  # blob missing (e.g. Azure serving deferred) — skip gracefully
    except Exception:
        logger.exception("image draft read failed for question %s", question_id)
        return False
    await _grade_pending_erd_question(
        db=db,
        user_id=user_id,
        question_id=question_id,
        image_bytes=img_bytes,
        image_key=img_draft.storage_key,
    )
    return True


async def _guarded_grade_pending_pair(
    *,
    user_id: int,
    question_id: int,
    live_image_bytes: Optional[bytes] = None,
    live_image_key: Optional[str] = None,
) -> int:
    """Grade one (user, question) pair — XML draft then image attempt — on its OWN DB
    session, under the shared concurrency semaphore. Returns the number of grades that
    actually ran (0–2); unchanged/empty drafts (and non-langgraph engines) are skipped.

    Concurrency discipline:
      - The semaphore is acquired BEFORE the session is opened, so a task waiting for a
        slot pins no pooled connection (nothing is checked out until the first query).
      - The pair uses a fresh ``SessionLocal`` — never the caller's request Session,
        which is a sync object and unsafe to share across concurrently-running pairs.
        ``_grade_pending_erd_question`` commits and releases that connection before its
        LLM stream, so at most ``ERD_GRADE_MAX_CONCURRENCY`` connections are ever live
        per worker, and never during the 30–90s grade itself.
      - Best-effort per sub-grade: a failure is logged, not raised, so ``gather`` never
        aborts sibling pairs.

    Image source: when ``live_image_bytes`` is given (finalize's currently-open
    question handing over its staged upload), that live image is graded as the second
    attempt and the persisted image draft is skipped so the same image isn't graded
    twice; otherwise the persisted image draft is graded (covers an upload on a
    navigated-away question).
    """
    graded = 0
    async with _erd_grade_semaphore():
        task_db = SessionLocal()
        try:
            has_live_image = live_image_bytes is not None
            # Snapshot the latest graded-submission time BEFORE the XML grade, which can
            # insert a fresh row the persisted-image skip must not compare against. A live
            # image is already known-changed (the client only hands one over when it
            # differs from the last submitted image), so it needs no snapshot.
            pre_grade_last_sub_at = (
                None
                if has_live_image
                else _latest_submission_at(task_db, user_id=user_id, question_id=question_id)
            )
            # XML draft first: grading it before the image means its "unchanged since last
            # submission" skip compares against submissions that predate this pass, not the
            # image attempt added next — so a genuine drawn answer is never skipped just
            # because an image is also present.
            try:
                if await _grade_pending_erd_question(
                    db=task_db, user_id=user_id, question_id=question_id,
                    image_bytes=None, image_key=None,
                ):
                    graded += 1
            except Exception:
                logger.exception(
                    "ER grade (xml) failed for user %s question %s", user_id, question_id
                )
            # Image as a SECOND attempt so a student who both drew and uploaded loses
            # neither — best-attempt scoring keeps the higher of the two rows.
            try:
                if has_live_image:
                    if await _grade_pending_erd_question(
                        db=task_db, user_id=user_id, question_id=question_id,
                        image_bytes=live_image_bytes, image_key=live_image_key,
                    ):
                        graded += 1
                elif await _grade_pending_image_draft(
                    db=task_db, user_id=user_id, question_id=question_id,
                    pre_grade_last_sub_at=pre_grade_last_sub_at,
                ):
                    graded += 1
            except Exception:
                logger.exception(
                    "ER grade (image) failed for user %s question %s", user_id, question_id
                )
        except Exception:
            # Snapshot / session setup failure for this pair: never let it abort the sweep.
            logger.exception(
                "ER grade pair failed for user %s question %s", user_id, question_id
            )
        finally:
            task_db.close()
    return graded


async def grade_pending_er_for_assessment(
    db: Session, assessment_id: int, user_ids: list[int]
) -> int:
    """Grade every roster student's latest stored ER draft for each ER item of this
    assessment, from server state. Grades BOTH the draw.io XML draft AND the autosaved
    uploaded-image draft (as separate best-of attempts), so the staff "Refresh scores" /
    force-submit path captures an image-only answer the same way the student's own
    end-of-assessment sweep does. Returns the number of (user, question) grades that
    actually ran; unchanged/empty drafts (and non-langgraph engines) are skipped.

    Runs pairs CONCURRENTLY, bounded by ``_erd_grade_semaphore`` (per-worker cap =
    ``settings.ERD_GRADE_MAX_CONCURRENCY``), so a class-sized sweep grades up to N
    diagrams at once without ever flooding the LLM past its token/min budget. Each pair
    runs on its OWN session (see ``_guarded_grade_pending_pair``) — the shared ``db`` is
    never used concurrently. The skip-unchanged / already-graded guard means untouched
    drafts make ZERO LLM calls, so only new/changed drafts hit the model. A single pair
    failing is logged and does not abort the batch.
    """
    er_question_ids = [
        item.item_id
        for item in db.query(AssessmentItem)
        .filter(
            AssessmentItem.assessment_id == assessment_id,
            AssessmentItem.item_type == "er_question",
        )
        .all()
    ]
    if not er_question_ids:
        return 0

    # Release the request session's pooled connection before the concurrent phase: each
    # pair grades on its own SessionLocal, and this function touches `db` no further.
    db.commit()

    results = await asyncio.gather(
        *[
            _guarded_grade_pending_pair(user_id=uid, question_id=qid)
            for uid in user_ids
            for qid in er_question_ids
        ],
        return_exceptions=True,
    )
    return sum(r for r in results if isinstance(r, int))


@router.post("/finalize-pending")
async def finalize_pending_er(
    request: Request,
    assessment_id: int = Form(...),
    image_question_id: Optional[int] = Form(None),
    erd_img: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Grade any unsubmitted/changed ER work for the caller's active assessment, as an
    end-of-assessment capture the frontend triggers right before finalizing.

    Trusted finalize path: unlike ``/submission`` it does **not** call
    ``enforce_not_expired``, so it still lands when fired at the buzzer. Grades each ER
    question's changed XML draft AND its autosaved image draft (an uploaded-image answer
    is persisted server-side the moment it is dropped, so an image staged on a question
    the student later navigated away from is still graded here — not just the currently
    open one). The currently-open question may also hand over its live staged image via
    ``erd_img`` + ``image_question_id`` as a race fallback for a drop-upload that hasn't
    landed yet; when it does, that question's persisted draft is skipped so the same
    image isn't graded twice. Credits the elapsed grading time once, and returns the
    pushed-forward ``end_time`` so the client can re-fold its timer before the subsequent
    finalize computes the weighted score.
    """
    from datetime import datetime, timezone

    from app.services.assessment_timer import (
        credit_query_time,
        get_active_assessment_session,
    )

    session = get_active_assessment_session(db, assessment_id, current_user.id)
    if session is None:
        return {"end_time": None}
    # Capture the id before the pre-grade commit expires the ORM object, so the
    # post-grade re-read below doesn't fire a lazy refresh on a stale instance.
    session_id = session.id

    credit_start = getattr(request.state, "received_at", None) or datetime.now(timezone.utc)

    er_question_ids = [
        item.item_id
        for item in db.query(AssessmentItem)
        .filter(
            AssessmentItem.assessment_id == assessment_id,
            AssessmentItem.item_type == "er_question",
        )
        .all()
    ]

    # Read the staged upload once (bytes for grading + a stored key for analytics). A
    # storage failure just leaves the key null; grading still runs on the bytes.
    image_bytes: Optional[bytes] = None
    image_key: Optional[str] = None
    if image_question_id is not None and erd_img is not None and getattr(erd_img, "filename", ""):
        try:
            await erd_img.seek(0)
            provider = get_er_storage_provider()
            image_key, _ = await asyncio.to_thread(provider.save, erd_img)
        except Exception:
            logger.exception("finalize-pending: image save failed; grading continues")
        try:
            await erd_img.seek(0)
            image_bytes = await erd_img.read()
        except Exception:
            image_bytes = None

    # Release the request session's pooled connection before the concurrent grading
    # phase: each question grades on its own SessionLocal (see _guarded_grade_pending_pair),
    # and we don't touch `db` again until the credit/re-read below.
    db.commit()

    # Grade every question CONCURRENTLY, bounded by the shared per-worker semaphore so a
    # whole-class finalize can't flood the LLM past its token/min budget. Each question
    # grades its XML draft then its image attempt (in that order) on its own session; the
    # currently-open question hands over its live staged image, all others use the
    # persisted image draft. Best-effort: a failing question is logged, never aborts the rest.
    await asyncio.gather(
        *[
            _guarded_grade_pending_pair(
                user_id=current_user.id,
                question_id=qid,
                live_image_bytes=(image_bytes if qid == image_question_id else None),
                live_image_key=(image_key if qid == image_question_id else None),
            )
            for qid in er_question_ids
        ],
        return_exceptions=True,
    )

    # Re-read the session: grades committed on fresh sessions leave this one's row
    # untouched, but a concurrent read may have lazily expired it mid-batch.
    session = (
        db.query(AssessmentSession).filter(AssessmentSession.id == session_id).first()
    )
    if session is None:
        return {"end_time": None}

    if session.is_active == 1:
        credit_query_time(db, session, credit_start)
        db.refresh(session)
    else:
        # Lazy expiry finalized us mid-batch and already computed weighted_score without
        # the grades above — recompute so the freshly captured ER work still counts.
        from app.models.assessment import Assessment as _Assessment
        from app.services import assessment_scoring

        assessment = (
            db.query(_Assessment).filter(_Assessment.id == assessment_id).first()
        )
        if assessment is not None:
            session.weighted_score = assessment_scoring.compute_weighted_score(
                db, assessment, current_user.id
            )
            db.commit()

    return {"end_time": session.end_time.isoformat() if session.end_time else None}


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
