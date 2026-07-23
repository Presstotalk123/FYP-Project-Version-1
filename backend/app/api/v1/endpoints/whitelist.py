from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.whitelist import WhitelistEntry
from app.schemas.whitelist import WhitelistEntryCreate, WhitelistEntryResponse
from app.dependencies import require_admin_role

router = APIRouter(prefix="/whitelist", tags=["whitelist"])


@router.get("", response_model=List[WhitelistEntryResponse])
def get_whitelist(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_role),
):
    return db.query(WhitelistEntry).all()


@router.post("", response_model=WhitelistEntryResponse, status_code=status.HTTP_201_CREATED)
def add_to_whitelist(
    request: WhitelistEntryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_role),
):
    email = request.email.lower()
    existing = db.query(WhitelistEntry).filter(WhitelistEntry.email == email).first()
    if existing:
        existing.role = request.role
        existing.name = request.name
        existing.class_group = request.class_group
        db.commit()
        db.refresh(existing)
        return existing

    entry = WhitelistEntry(
        email=email,
        role=request.role,
        name=request.name,
        class_group=request.class_group,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_whitelist(
    entry_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_role),
):
    entry = db.query(WhitelistEntry).filter(WhitelistEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    db.delete(entry)
    db.commit()
