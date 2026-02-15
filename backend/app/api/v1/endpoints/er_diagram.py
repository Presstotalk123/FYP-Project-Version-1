import json
import re
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.user import User
from app.schemas.er_diagram import (
    DifficultyLabel,
    ERDiagramQuestionResponse,
    ERDiagramQuestionListItem,
    GenerateRubricMode,
    GenerateRubricResponse,
)
from app.utils.er_storage import get_er_storage_provider

router = APIRouter(prefix="/er-diagram", tags=["er-diagram"])


def _is_placeholder_value(value: str, field_name: str) -> bool:
    normalized = value.strip().lower()
    target = field_name.strip().lower()
    placeholder_patterns = {
        target,
        f"{{{{{target}}}}}",
        f"{{{{ {target} }}}}",
        f"<{target}>",
        f"[{target}]",
    }
    return normalized in placeholder_patterns


def _build_dify_headers(content_type: Optional[str] = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "DatabaseAssist/1.0",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if settings.DIFY_ER_RUBRIC_API_KEY:
        headers["Authorization"] = f"Bearer {settings.DIFY_ER_RUBRIC_API_KEY}"
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
    else:
        path = f"{path}/files/upload"
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, parsed.fragment))


def _upload_model_answer_to_dify(model_answer: UploadFile) -> str:
    filename = model_answer.filename or "model_answer"
    content_type = model_answer.content_type or "application/octet-stream"
    user_ref = "databaseassist-er-rubric"
    file_bytes = model_answer.file.read()
    model_answer.file.seek(0)
    headers = _build_dify_headers()
    upload_url = _derive_files_upload_url(settings.DIFY_ER_RUBRIC_URL or "")

    try:
        with httpx.Client(timeout=float(settings.DIFY_ER_RUBRIC_TIMEOUT_SECONDS)) as client:
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
    if model_answer:
        upload_file_id = _upload_model_answer_to_dify(model_answer)
        files.append(
            {
                "type": "image",
                "transfer_method": "local_file",
                "upload_file_id": upload_file_id,
            }
        )

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
        },
        "response_mode": "blocking",
        "user": "databaseassist-er-rubric",
        "files": files,
    }

    headers = _build_dify_headers("application/json")

    try:
        with httpx.Client(timeout=float(settings.DIFY_ER_RUBRIC_TIMEOUT_SECONDS)) as client:
            response = client.post(
                settings.DIFY_ER_RUBRIC_URL,
                json=workflow_payload,
                headers=headers,
            )
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
        raise _format_dify_http_error("request", response.status_code, response.text)

    try:
        payload = response.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify response is not valid JSON",
        )

    outputs = payload
    if isinstance(payload.get("data"), dict):
        data_section = payload["data"]
        status_value = data_section.get("status")
        error_value = data_section.get("error")
        if status_value and status_value != "succeeded":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Dify workflow failed with status '{status_value}': {error_value}",
            )
        if isinstance(data_section.get("outputs"), dict):
            outputs = data_section["outputs"]

    rubric_md = outputs.get("rubric_md") if isinstance(outputs, dict) else None
    if not isinstance(rubric_md, str) or not rubric_md.strip():
        output_keys = list(outputs.keys()) if isinstance(outputs, dict) else []
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dify response missing non-empty rubric_md. Available output keys: {output_keys}",
        )

    difficulty = outputs.get("difficulty") if isinstance(outputs, dict) else None
    if not isinstance(difficulty, dict):
        output_keys = list(outputs.keys()) if isinstance(outputs, dict) else []
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Dify response missing difficulty object. Available output keys: {output_keys}",
        )

    label = difficulty.get("label")
    rationale = difficulty.get("rationale")
    if label not in {"Easy", "Medium", "Hard"} or not isinstance(rationale, str) or not rationale.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify response has invalid difficulty payload",
        )

    rubric_json = outputs.get("rubric_json") if isinstance(outputs, dict) else None
    if rubric_json is None:
        rubric_json = {}
    if not isinstance(rubric_json, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Dify response rubric_json must be an object",
        )

    diff_summary = outputs.get("diff_summary") if isinstance(outputs, dict) else None
    if diff_summary is None:
        diff_summary = []
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


def _parse_json_field(value: str, field_name: str) -> Any:
    try:
        return json.loads(value)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be valid JSON",
        )


def _to_response(question: ERDiagramQuestion) -> ERDiagramQuestionResponse:
    rubric_json = _parse_json_field(question.rubric_json, "rubric_json")
    instruction_history = _parse_json_field(question.instruction_history_json, "instruction_history")

    if not isinstance(rubric_json, dict):
        rubric_json = {}
    if not isinstance(instruction_history, list):
        instruction_history = []

    instruction_history = [str(item) for item in instruction_history if str(item).strip()]

    return ERDiagramQuestionResponse(
        id=question.id,
        title=question.title,
        problem_statement=question.problem_statement,
        notation=question.notation,
        difficulty_label=question.difficulty_label,
        difficulty_rationale=question.difficulty_rationale,
        rubric_md=question.rubric_md,
        rubric_json=rubric_json,
        instruction_history=instruction_history,
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    del db
    del current_user

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
    if _is_placeholder_value(statement, "Problem_Statement"):
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
    model_answer: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
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
        rubric_json=json.dumps(parsed_rubric_json),
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
    del current_user
    questions = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.is_deleted == 0)
        .order_by(ERDiagramQuestion.created_at.desc())
        .all()
    )
    return questions


@router.get("/questions/{question_id}", response_model=ERDiagramQuestionResponse)
def get_er_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    del current_user
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )

    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    return _to_response(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_er_question(
    question_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    del current_user
    question = (
        db.query(ERDiagramQuestion)
        .filter(ERDiagramQuestion.id == question_id, ERDiagramQuestion.is_deleted == 0)
        .first()
    )

    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    question.is_deleted = 1
    db.commit()

    return None
