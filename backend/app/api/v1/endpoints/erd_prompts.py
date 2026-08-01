"""Admin-editable LangGraph prompt overrides (staff/admin only).

Versioned overrides of the code-default prompts in
app.services.erd_tutor.prompts, resolved at call time by
app.services.erd_tutor.prompt_store.get_prompt. History is append-only:
saves insert new versions, restore/reset only flip is_active flags.
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
# Same staff-or-admin gate the other admin endpoint modules use.
from app.dependencies import require_staff_role as require_staff
from app.models.erd_prompt_version import ErdPromptVersion
from app.models.user import User
from app.schemas.erd_prompt import (
    ErdPromptListItem,
    ErdPromptResetResponse,
    ErdPromptVersionSummary,
)
from app.services.erd_tutor.prompt_store import PROMPT_REGISTRY

router = APIRouter(prefix="/erd-prompts", tags=["erd-prompts"])

MAX_PROMPT_CHARS = 20_000


class PromptUpdate(BaseModel):
    content: str


def _registry_or_404(key: str) -> dict:
    entry = PROMPT_REGISTRY.get(key)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Unknown prompt key '{key}'")
    return entry


def _active_row(db: Session, key: str):
    return (db.query(ErdPromptVersion)
              .filter(ErdPromptVersion.prompt_key == key,
                      ErdPromptVersion.is_active == 1)
              .first())


def _deactivate_active(db: Session, key: str) -> None:
    """Flip is_active off for the (at most one) currently-active row of `key`."""
    db.query(ErdPromptVersion).filter(
        ErdPromptVersion.prompt_key == key,
        ErdPromptVersion.is_active == 1,
    ).update({"is_active": 0})


def _emails_by_id(db: Session, rows) -> Dict[int, str]:
    """Batch-resolve created_by user ids to emails in a single query."""
    ids = {r.created_by for r in rows}
    if not ids:
        return {}
    pairs = (db.query(User.id, User.email)
               .filter(User.id.in_(ids))
               .all())
    return {uid: email for uid, email in pairs}


def _version_summary(row: ErdPromptVersion, email: Optional[str]) -> dict:
    return {
        "version_no": row.version_no,
        "content": row.content,
        "created_by_email": email,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "is_active": bool(row.is_active),
    }


@router.get("", response_model=List[ErdPromptListItem])
def list_prompts(db: Session = Depends(get_db),
                 current_user: User = Depends(require_staff)):
    out = []
    actives = {}
    for key in PROMPT_REGISTRY:
        active = _active_row(db, key)
        if active is not None:
            actives[key] = active
    emails = _emails_by_id(db, actives.values())
    for key, entry in PROMPT_REGISTRY.items():
        active = actives.get(key)
        out.append({
            "key": key,
            "label": entry["label"],
            "description": entry["description"],
            "default_content": entry["default"],
            "is_overridden": active is not None,
            "active": _version_summary(active, emails.get(active.created_by)) if active else None,
        })
    return out


@router.get("/{key}/versions", response_model=List[ErdPromptVersionSummary])
def list_versions(key: str, db: Session = Depends(get_db),
                  current_user: User = Depends(require_staff)):
    _registry_or_404(key)
    rows = (db.query(ErdPromptVersion)
              .filter(ErdPromptVersion.prompt_key == key)
              .order_by(ErdPromptVersion.version_no.desc())
              .all())
    emails = _emails_by_id(db, rows)
    return [_version_summary(r, emails.get(r.created_by)) for r in rows]


@router.put("/{key}", response_model=ErdPromptVersionSummary)
def save_prompt(key: str, payload: PromptUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(require_staff)):
    _registry_or_404(key)
    if not payload.content.strip():
        raise HTTPException(status_code=422, detail="Prompt content must not be empty")
    if len(payload.content) > MAX_PROMPT_CHARS:
        raise HTTPException(status_code=422,
                            detail=f"Prompt content exceeds {MAX_PROMPT_CHARS} characters")

    for attempt in range(2):
        max_no = (db.query(func.max(ErdPromptVersion.version_no))
                    .filter(ErdPromptVersion.prompt_key == key)
                    .scalar()) or 0
        _deactivate_active(db, key)
        row = ErdPromptVersion(prompt_key=key, version_no=max_no + 1,
                               content=payload.content,
                               created_by=current_user.id, is_active=1)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if attempt == 1:
                raise HTTPException(
                    status_code=409,
                    detail="Another admin saved a new version at the same time — reload and try again.",
                )
            continue
        else:
            db.refresh(row)
            return _version_summary(row, current_user.email)


@router.post("/{key}/versions/{version_no}/activate", response_model=ErdPromptVersionSummary)
def activate_version(key: str, version_no: int, db: Session = Depends(get_db),
                     current_user: User = Depends(require_staff)):
    _registry_or_404(key)
    row = (db.query(ErdPromptVersion)
             .filter(ErdPromptVersion.prompt_key == key,
                     ErdPromptVersion.version_no == version_no)
             .first())
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Version {version_no} not found for '{key}'")
    _deactivate_active(db, key)
    row.is_active = 1
    db.commit()
    db.refresh(row)
    emails = _emails_by_id(db, [row])
    return _version_summary(row, emails.get(row.created_by))


@router.delete("/{key}/override", response_model=ErdPromptResetResponse)
def reset_to_default(key: str, db: Session = Depends(get_db),
                     current_user: User = Depends(require_staff)):
    _registry_or_404(key)
    _deactivate_active(db, key)
    db.commit()
    return {"key": key, "is_overridden": False}
