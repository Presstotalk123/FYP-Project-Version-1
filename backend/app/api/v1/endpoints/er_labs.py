from datetime import datetime
from typing import List, Optional
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.er_lab import ErLab
from app.models.er_lab_session import ErLabSession
from app.models.er_lab_question import ErLabQuestion
from app.models.er_lab_submission import ErLabSubmission
from app.schemas.er_lab import (
    ErLabCreate, ErLabUpdate, ErLabResponse, ErLabStaffDetail,
    ErLabQuestionCreate, ErLabQuestionUpdate, ErLabQuestionResponse,
    ErLabSessionStart, ErLabSessionResponse,
    ErLabSubmissionResponse, ErLabQuestionBestScore, ErLabMyScoresResponse,
    ErLabStudentSummary, ErLabStudentsResponse,
    ErLabOverrideRequest,
)
from app.utils.er_storage import get_er_storage_provider

router = APIRouter(prefix="/er-labs", tags=["er-labs"])
logger = logging.getLogger(__name__)


def _to_response(lab: ErLab) -> ErLabResponse:
    return ErLabResponse(
        id=lab.id,
        title=lab.title,
        description=lab.description,
        is_published=bool(lab.is_published),
        is_running=bool(lab.is_running),
        created_at=lab.created_at,
        updated_at=lab.updated_at,
    )


def _terminate_all_active_sessions(lab_id: int, db: Session) -> int:
    sessions = db.query(ErLabSession).filter(
        ErLabSession.er_lab_id == lab_id,
        ErLabSession.is_active == 1,
    ).all()
    now = datetime.utcnow()
    for s in sessions:
        s.is_active = 0
        s.ended_at = now
    db.commit()
    return len(sessions)


# ===== Lab CRUD =====

@router.post("", response_model=ErLabStaffDetail, status_code=status.HTTP_201_CREATED)
def create_er_lab(
    body: ErLabCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    lab = ErLab(
        title=body.title,
        description=body.description,
        join_password_plain=body.join_password,
        join_password_hash=hash_password(body.join_password),
        created_by=current_user.id,
    )
    db.add(lab)
    db.commit()
    db.refresh(lab)

    return ErLabStaffDetail(
        **_to_response(lab).model_dump(),
        join_password=lab.join_password_plain,
    )


@router.get("", response_model=List[ErLabResponse])
def list_er_labs(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(ErLab).filter(ErLab.is_deleted == 0)
    if current_user.role.value == "student":
        q = q.filter(ErLab.is_published == 1)
    labs = q.order_by(ErLab.created_at.desc()).offset(skip).limit(limit).all()
    return [_to_response(l) for l in labs]


@router.get("/{lab_id}")
def get_er_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    if current_user.role.value == "student":
        if not lab.is_published:
            raise HTTPException(status_code=404, detail="Lab not found")
        return _to_response(lab)

    return ErLabStaffDetail(
        **_to_response(lab).model_dump(),
        join_password=lab.join_password_plain,
    )


@router.put("/{lab_id}", response_model=ErLabResponse)
def update_er_lab(
    lab_id: int,
    body: ErLabUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    if lab.is_running:
        raise HTTPException(status_code=400, detail="Cannot edit lab while it is running. Stop the lab first.")

    if body.title is not None:
        lab.title = body.title
    if body.description is not None:
        lab.description = body.description
    if body.join_password is not None:
        lab.join_password_plain = body.join_password
        lab.join_password_hash = hash_password(body.join_password)

    lab.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lab)
    return _to_response(lab)


@router.delete("/{lab_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_er_lab(
    lab_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    if lab.is_running:
        _terminate_all_active_sessions(lab_id, db)
        lab.is_running = 0
    lab.is_deleted = 1
    lab.updated_at = datetime.utcnow()
    db.commit()
    return None


# ===== State management =====

@router.post("/{lab_id}/publish", response_model=ErLabResponse)
def publish_er_lab(lab_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_staff_role)):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    lab.is_published = 1
    lab.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lab)
    return _to_response(lab)


@router.post("/{lab_id}/unpublish", response_model=ErLabResponse)
def unpublish_er_lab(lab_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_staff_role)):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    if lab.is_running:
        _terminate_all_active_sessions(lab_id, db)
        lab.is_running = 0
    lab.is_published = 0
    lab.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lab)
    return _to_response(lab)


@router.post("/{lab_id}/start", response_model=ErLabResponse)
def start_er_lab(lab_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_staff_role)):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    if not lab.is_published:
        raise HTTPException(status_code=400, detail="Lab must be published before starting")
    lab.is_running = 1
    lab.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lab)
    return _to_response(lab)


@router.post("/{lab_id}/stop")
def stop_er_lab(lab_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_staff_role)):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    terminated = _terminate_all_active_sessions(lab_id, db)
    lab.is_running = 0
    lab.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Lab stopped", "sessions_terminated": terminated}


# ===== Question CRUD =====

RUBRIC_INTERNAL_META_KEY = "__dbassist_meta"
SHOW_RUBRIC_ON_ATTEMPT_KEY = "show_rubric_on_attempt"


def _with_show_rubric_meta(rubric_json: dict, show: bool) -> dict:
    merged = dict(rubric_json)
    meta = merged.get(RUBRIC_INTERNAL_META_KEY)
    if not isinstance(meta, dict):
        meta = {}
    meta[SHOW_RUBRIC_ON_ATTEMPT_KEY] = bool(show)
    merged[RUBRIC_INTERNAL_META_KEY] = meta
    return merged


def _extract_show_rubric(rubric_json: dict) -> bool:
    meta = rubric_json.get(RUBRIC_INTERNAL_META_KEY)
    if not isinstance(meta, dict):
        return False
    return bool(meta.get(SHOW_RUBRIC_ON_ATTEMPT_KEY, False))


def _strip_meta(rubric_json: dict) -> dict:
    cleaned = dict(rubric_json)
    cleaned.pop(RUBRIC_INTERNAL_META_KEY, None)
    return cleaned


def _question_to_response(q: ErLabQuestion, *, hide_rubric_when_disabled: bool) -> ErLabQuestionResponse:
    rubric = json.loads(q.rubric_json) if q.rubric_json else {}
    show = _extract_show_rubric(rubric)
    rubric_for_response = None
    rubric_md_for_response = None
    if not hide_rubric_when_disabled or show:
        rubric_for_response = _strip_meta(rubric)
        rubric_md_for_response = q.rubric_md
    return ErLabQuestionResponse(
        id=q.id,
        er_lab_id=q.er_lab_id,
        order_index=q.order_index,
        title=q.title,
        problem_statement=q.problem_statement,
        notation=q.notation,
        difficulty_label=q.difficulty_label,
        difficulty_rationale=q.difficulty_rationale,
        rubric_md=rubric_md_for_response,
        rubric_json=rubric_for_response,
        instruction_history=json.loads(q.instruction_history_json or "[]"),
        model_answer_storage_key=q.model_answer_storage_key,
        model_answer_url=q.model_answer_url,
        show_rubric_on_attempt=show,
        created_by=q.created_by,
        created_at=q.created_at,
        updated_at=q.updated_at,
    )


@router.post("/{lab_id}/questions", response_model=ErLabQuestionResponse, status_code=201)
def create_er_lab_question(
    lab_id: int,
    title: str = Form(...),
    problem_statement: str = Form(...),
    notation: str = Form("Chen"),
    difficulty_label: str = Form(...),
    difficulty_rationale: str = Form(...),
    rubric_md: str = Form(...),
    rubric_json: str = Form(...),
    instruction_history: str = Form("[]"),
    order_index: int = Form(0),
    show_rubric_on_attempt: bool = Form(False),
    model_answer: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    if lab.is_running:
        raise HTTPException(status_code=400, detail="Cannot add questions while lab is running")

    try:
        rubric_json_obj = json.loads(rubric_json) if rubric_json else {}
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="rubric_json must be valid JSON")
    try:
        instruction_history_list = json.loads(instruction_history) if instruction_history else []
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="instruction_history must be a JSON array")

    if not isinstance(rubric_json_obj, dict):
        raise HTTPException(status_code=400, detail="rubric_json must be a JSON object")
    if not isinstance(instruction_history_list, list):
        raise HTTPException(status_code=400, detail="instruction_history must be a JSON array")

    storage_key: Optional[str] = None
    storage_url: Optional[str] = None
    if model_answer is not None and model_answer.filename:
        provider = get_er_storage_provider()
        storage_key, storage_url = provider.save(model_answer)

    rubric_with_meta = _with_show_rubric_meta(rubric_json_obj, show_rubric_on_attempt)
    q = ErLabQuestion(
        er_lab_id=lab_id,
        order_index=order_index,
        title=title,
        problem_statement=problem_statement,
        notation=notation,
        difficulty_label=difficulty_label,
        difficulty_rationale=difficulty_rationale,
        rubric_md=rubric_md,
        rubric_json=json.dumps(rubric_with_meta, ensure_ascii=False),
        instruction_history_json=json.dumps(instruction_history_list, ensure_ascii=False),
        model_answer_storage_key=storage_key,
        model_answer_url=storage_url,
        created_by=current_user.id,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return _question_to_response(q, hide_rubric_when_disabled=False)


@router.get("/{lab_id}/questions", response_model=List[ErLabQuestionResponse])
def list_er_lab_questions(
    lab_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    if current_user.role.value == "student" and not lab.is_published:
        raise HTTPException(status_code=404, detail="Lab not found")

    qs = db.query(ErLabQuestion).filter(
        ErLabQuestion.er_lab_id == lab_id, ErLabQuestion.is_deleted == 0,
    ).order_by(ErLabQuestion.order_index, ErLabQuestion.created_at).all()

    hide = current_user.role.value == "student"
    return [_question_to_response(q, hide_rubric_when_disabled=hide) for q in qs]


@router.get("/{lab_id}/questions/{qid}", response_model=ErLabQuestionResponse)
def get_er_lab_question(
    lab_id: int, qid: int,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    q = db.query(ErLabQuestion).filter(
        ErLabQuestion.id == qid, ErLabQuestion.er_lab_id == lab_id, ErLabQuestion.is_deleted == 0,
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if current_user.role.value == "student" and (not lab or not lab.is_published):
        raise HTTPException(status_code=404, detail="Question not found")
    hide = current_user.role.value == "student"
    return _question_to_response(q, hide_rubric_when_disabled=hide)


@router.put("/{lab_id}/questions/{qid}", response_model=ErLabQuestionResponse)
def update_er_lab_question(
    lab_id: int, qid: int,
    title: Optional[str] = Form(None),
    problem_statement: Optional[str] = Form(None),
    difficulty_label: Optional[str] = Form(None),
    difficulty_rationale: Optional[str] = Form(None),
    rubric_md: Optional[str] = Form(None),
    rubric_json: Optional[str] = Form(None),
    instruction_history: Optional[str] = Form(None),
    order_index: Optional[int] = Form(None),
    show_rubric_on_attempt: Optional[bool] = Form(None),
    model_answer: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    if lab.is_running:
        raise HTTPException(status_code=400, detail="Cannot edit questions while lab is running")
    q = db.query(ErLabQuestion).filter(
        ErLabQuestion.id == qid, ErLabQuestion.er_lab_id == lab_id, ErLabQuestion.is_deleted == 0,
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    if title is not None:
        q.title = title
    if problem_statement is not None:
        q.problem_statement = problem_statement
    if difficulty_label is not None:
        q.difficulty_label = difficulty_label
    if difficulty_rationale is not None:
        q.difficulty_rationale = difficulty_rationale
    if rubric_md is not None:
        q.rubric_md = rubric_md
    if order_index is not None:
        q.order_index = order_index

    existing_rubric = json.loads(q.rubric_json) if q.rubric_json else {}
    next_rubric_dict: dict
    if rubric_json is not None:
        try:
            parsed = json.loads(rubric_json)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="rubric_json must be valid JSON")
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="rubric_json must be a JSON object")
        next_rubric_dict = parsed
    else:
        next_rubric_dict = _strip_meta(existing_rubric)
    next_show = show_rubric_on_attempt if show_rubric_on_attempt is not None else _extract_show_rubric(existing_rubric)
    q.rubric_json = json.dumps(_with_show_rubric_meta(next_rubric_dict, next_show), ensure_ascii=False)

    if instruction_history is not None:
        try:
            parsed_history = json.loads(instruction_history)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="instruction_history must be a JSON array")
        if not isinstance(parsed_history, list):
            raise HTTPException(status_code=400, detail="instruction_history must be a JSON array")
        q.instruction_history_json = json.dumps(parsed_history, ensure_ascii=False)

    if model_answer is not None and model_answer.filename:
        provider = get_er_storage_provider()
        if q.model_answer_storage_key:
            try:
                provider.delete(q.model_answer_storage_key)
            except Exception as exc:
                logger.warning("Failed to delete previous model answer %s: %s", q.model_answer_storage_key, exc)
        new_key, new_url = provider.save(model_answer)
        q.model_answer_storage_key = new_key
        q.model_answer_url = new_url

    q.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(q)
    return _question_to_response(q, hide_rubric_when_disabled=False)


@router.delete("/{lab_id}/questions/{qid}", status_code=204)
def delete_er_lab_question(
    lab_id: int, qid: int,
    db: Session = Depends(get_db), current_user: User = Depends(require_staff_role),
):
    q = db.query(ErLabQuestion).filter(
        ErLabQuestion.id == qid, ErLabQuestion.er_lab_id == lab_id, ErLabQuestion.is_deleted == 0,
    ).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    q.is_deleted = 1
    q.updated_at = datetime.utcnow()
    db.commit()
    return None


# ===== Session lifecycle =====

def _session_to_response(s: ErLabSession) -> ErLabSessionResponse:
    return ErLabSessionResponse(
        id=s.id, er_lab_id=s.er_lab_id, user_id=s.user_id,
        is_active=bool(s.is_active), started_at=s.started_at, ended_at=s.ended_at,
    )


@router.post("/{lab_id}/session/start", response_model=ErLabSessionResponse)
def start_er_lab_session(
    lab_id: int, body: ErLabSessionStart,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    is_staff = current_user.role.value == "staff"
    if not is_staff:
        if not lab.is_published or not lab.is_running:
            raise HTTPException(status_code=400, detail="Lab is not available for sessions")
        if not verify_password(body.join_password or "", lab.join_password_hash):
            raise HTTPException(status_code=401, detail="Incorrect join password")

    existing = db.query(ErLabSession).filter(
        ErLabSession.er_lab_id == lab_id,
        ErLabSession.user_id == current_user.id,
        ErLabSession.is_active == 1,
    ).first()
    if existing:
        return _session_to_response(existing)

    try:
        s = ErLabSession(er_lab_id=lab_id, user_id=current_user.id, is_active=1)
        db.add(s)
        db.commit()
        db.refresh(s)
        return _session_to_response(s)
    except IntegrityError:
        db.rollback()
        s = db.query(ErLabSession).filter(
            ErLabSession.er_lab_id == lab_id,
            ErLabSession.user_id == current_user.id,
            ErLabSession.is_active == 1,
        ).first()
        if not s:
            raise HTTPException(status_code=500, detail="Failed to create or retrieve session")
        return _session_to_response(s)


@router.get("/{lab_id}/session", response_model=ErLabSessionResponse)
def get_er_lab_session(
    lab_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.query(ErLabSession).filter(
        ErLabSession.er_lab_id == lab_id,
        ErLabSession.user_id == current_user.id,
        ErLabSession.is_active == 1,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="No active session found")
    return _session_to_response(s)


@router.post("/{lab_id}/session/exit")
def exit_er_lab_session(
    lab_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.query(ErLabSession).filter(
        ErLabSession.er_lab_id == lab_id,
        ErLabSession.user_id == current_user.id,
        ErLabSession.is_active == 1,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="No active session found")
    s.is_active = 0
    s.ended_at = datetime.utcnow()
    db.commit()
    return {"message": "Session ended"}


# ===== Scoring reads =====

def _submission_to_response(sub: ErLabSubmission) -> ErLabSubmissionResponse:
    return ErLabSubmissionResponse(
        id=sub.id, er_lab_question_id=sub.er_lab_question_id, er_lab_id=sub.er_lab_id,
        user_id=sub.user_id, session_id=sub.session_id,
        submitted_xml=sub.submitted_xml,
        submitted_image_storage_key=sub.submitted_image_storage_key,
        auto_score_earned=sub.auto_score_earned, auto_score_total=sub.auto_score_total,
        auto_score_percent=sub.auto_score_percent, auto_score_label=sub.auto_score_label,
        auto_checks_json=json.loads(sub.auto_checks_json) if sub.auto_checks_json else [],
        auto_graded_at=sub.auto_graded_at,
        override_score_earned=sub.override_score_earned, override_score_total=sub.override_score_total,
        override_score_percent=sub.override_score_percent,
        override_reason=sub.override_reason,
        overridden_by=sub.overridden_by, overridden_at=sub.overridden_at,
        submitted_at=sub.submitted_at,
    )


def _resolve_target_user(student_id: Optional[int], current_user: User) -> int:
    if student_id is not None:
        if current_user.role.value != "staff":
            raise HTTPException(status_code=403, detail="Staff only")
        return student_id
    return current_user.id


@router.get("/{lab_id}/my-submissions", response_model=List[ErLabSubmissionResponse])
def list_my_submissions(
    lab_id: int, student_id: Optional[int] = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    user_id = _resolve_target_user(student_id, current_user)
    rows = db.query(ErLabSubmission).filter(
        ErLabSubmission.er_lab_id == lab_id,
        ErLabSubmission.user_id == user_id,
    ).order_by(ErLabSubmission.submitted_at.asc()).all()
    return [_submission_to_response(r) for r in rows]


@router.get("/{lab_id}/my-scores", response_model=ErLabMyScoresResponse)
def get_my_scores(
    lab_id: int, student_id: Optional[int] = None,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    user_id = _resolve_target_user(student_id, current_user)

    questions = db.query(ErLabQuestion).filter(
        ErLabQuestion.er_lab_id == lab_id, ErLabQuestion.is_deleted == 0,
    ).order_by(ErLabQuestion.order_index, ErLabQuestion.created_at).all()

    all_subs = db.query(ErLabSubmission).filter(
        ErLabSubmission.er_lab_id == lab_id,
        ErLabSubmission.user_id == user_id,
    ).all()

    by_q: dict[int, list[ErLabSubmission]] = {}
    for s in all_subs:
        by_q.setdefault(s.er_lab_question_id, []).append(s)

    out: list[ErLabQuestionBestScore] = []
    total_earned = 0.0
    total_total = 0.0
    for q in questions:
        subs = by_q.get(q.id, [])
        if not subs:
            out.append(ErLabQuestionBestScore(
                er_lab_question_id=q.id, best_percent=None, best_earned=None,
                best_total=None, attempts=0, last_attempted_at=None,
            ))
            continue
        def _eff_pct(s: ErLabSubmission) -> float:
            return s.override_score_percent if s.override_score_percent is not None else s.auto_score_percent
        def _eff_earned(s: ErLabSubmission) -> float:
            return s.override_score_earned if s.override_score_earned is not None else s.auto_score_earned
        def _eff_total(s: ErLabSubmission) -> float:
            return s.override_score_total if s.override_score_total is not None else s.auto_score_total

        best = max(subs, key=_eff_pct)
        earned = _eff_earned(best)
        total = _eff_total(best)
        out.append(ErLabQuestionBestScore(
            er_lab_question_id=q.id,
            best_percent=_eff_pct(best), best_earned=earned, best_total=total,
            attempts=len(subs),
            last_attempted_at=max(s.submitted_at for s in subs),
        ))
        total_earned += earned
        total_total += total

    return ErLabMyScoresResponse(
        er_lab_id=lab_id, user_id=user_id, questions=out,
        total_earned=total_earned, total_total=total_total,
    )


@router.get("/{lab_id}/students", response_model=ErLabStudentsResponse)
def list_er_lab_students(
    lab_id: int, db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    lab = db.query(ErLab).filter(ErLab.id == lab_id, ErLab.is_deleted == 0).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    total_q = db.query(ErLabQuestion).filter(
        ErLabQuestion.er_lab_id == lab_id, ErLabQuestion.is_deleted == 0,
    ).count()

    user_ids = [
        uid for (uid,) in db.query(ErLabSubmission.user_id)
        .filter(ErLabSubmission.er_lab_id == lab_id).distinct().all()
    ]

    students = []
    for uid in user_ids:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            continue
        scores = get_my_scores(lab_id, student_id=uid, db=db, current_user=current_user)
        attempts = sum(q.attempts for q in scores.questions)
        last = max(
            (q.last_attempted_at for q in scores.questions if q.last_attempted_at),
            default=None,
        )
        students.append(ErLabStudentSummary(
            user_id=uid, email=user.email,
            total_earned=scores.total_earned, total_total=scores.total_total,
            attempts=attempts, last_submission_at=last,
        ))
    students.sort(key=lambda s: (s.last_submission_at or datetime.min), reverse=True)

    return ErLabStudentsResponse(
        er_lab_id=lab_id, lab_title=lab.title, total_questions=total_q, students=students,
    )


# ===== Staff override =====

override_router = APIRouter(prefix="/er-lab-submissions", tags=["er-labs"])


@override_router.post("/{submission_id}/override", response_model=ErLabSubmissionResponse)
def set_override(
    submission_id: int, body: ErLabOverrideRequest,
    db: Session = Depends(get_db), current_user: User = Depends(require_staff_role),
):
    sub = db.query(ErLabSubmission).filter(ErLabSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub.override_score_earned = body.score_earned
    sub.override_score_total = body.score_total
    sub.override_score_percent = (body.score_earned / body.score_total) * 100.0
    sub.override_reason = body.reason
    sub.overridden_by = current_user.id
    sub.overridden_at = datetime.utcnow()
    db.commit()
    db.refresh(sub)
    return _submission_to_response(sub)


@override_router.delete("/{submission_id}/override", response_model=ErLabSubmissionResponse)
def clear_override(
    submission_id: int,
    db: Session = Depends(get_db), current_user: User = Depends(require_staff_role),
):
    sub = db.query(ErLabSubmission).filter(ErLabSubmission.id == submission_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub.override_score_earned = None
    sub.override_score_total = None
    sub.override_score_percent = None
    sub.override_reason = None
    sub.overridden_by = None
    sub.overridden_at = None
    db.commit()
    db.refresh(sub)
    return _submission_to_response(sub)
