from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.whitelist import WhitelistEntry
from app.schemas.whitelist import WhitelistEntryCreate, WhitelistEntryResponse, WhitelistEntryUpdate
from app.dependencies import require_admin_role
from app.services.excel_parser import parse_students_from_excel
from typing import Dict, Any

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
        
        # Sync to existing user if they have already signed in before
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.role = request.role
            user.name = request.name
            user.class_group = request.class_group
            
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
    
    # Sync to existing user if they have already signed in before
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.role = request.role
        user.name = request.name
        user.class_group = request.class_group
        
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


@router.put("/{entry_id}", response_model=WhitelistEntryResponse)
def update_whitelist_entry(
    entry_id: int,
    request: WhitelistEntryUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_role),
):
    entry = db.query(WhitelistEntry).filter(WhitelistEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")

    entry.name = request.name
    entry.class_group = request.class_group
    
    # Sync to existing user if they have already signed in before
    user = db.query(User).filter(User.email == entry.email).first()
    if user:
        user.name = request.name
        user.class_group = request.class_group
        
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/upload")
async def upload_students(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin_role),
):
    try:
        contents = await file.read()
        students = parse_students_from_excel(contents, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    imported = 0
    skipped = []
    failed = []

    for idx, student in enumerate(students):
        try:
            email = student["email"]
            name = student["name"]
            class_group = student["class_group"]
            role = "student"

            existing = db.query(WhitelistEntry).filter(WhitelistEntry.email == email).first()
            if existing:
                skipped.append({"email": email, "reason": "already exists"})
                continue

            entry = WhitelistEntry(
                email=email,
                role=role,
                name=name,
                class_group=class_group,
            )
            db.add(entry)
            
            # Sync to existing user if they have already signed in before
            user_db = db.query(User).filter(User.email == email).first()
            if user_db:
                user_db.role = role
                user_db.name = name
                user_db.class_group = class_group
                
            db.commit()
            imported += 1
        except Exception as e:
            db.rollback()
            failed.append({"email": student.get("email", f"row {idx}"), "reason": str(e)})

    return {
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
    }

