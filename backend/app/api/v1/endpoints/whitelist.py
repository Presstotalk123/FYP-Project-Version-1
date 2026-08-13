from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.whitelist import WhitelistEntry
from app.schemas.whitelist import (
    WhitelistEntryCreate,
    WhitelistEntryResponse,
    WhitelistEntryUpdate,
    ParsedStudent,
    UploadAddition,
    UploadUpdate,
    UploadRemoval,
    UploadPreviewResponse,
    UploadConfirmRequest,
    UploadConfirmResponse,
)
from app.dependencies import require_admin_role
from app.services.excel_parser import parse_students_from_excel
from typing import Dict, Any

router = APIRouter(prefix="/whitelist", tags=["whitelist"])

# Class group exempt from upload-driven removal, no matter what the sheet
# contains — used for test/seed accounts that don't come from a real roster.
PROTECTED_CLASS_GROUP = "TEST"


def _build_upload_diff(db: Session, students: list[dict], acting_admin_email: str):
    """Shared by the preview and confirm endpoints so their classification of
    rows can never drift apart. `students` is the raw parsed sheet
    (list of {name, email, class_group}).

    Existence is checked against ALL whitelist entries (email is unique across
    roles), but updates and removals are confined to student-role entries so a
    roster upload never mutates or deletes a staff/admin account.
    """
    by_email = {s["email"]: s for s in students}

    existing_all = db.query(WhitelistEntry).all()
    existing_by_email = {e.email: e for e in existing_all}

    to_add: list[dict] = []
    to_update: list[dict] = []
    for email, sheet_row in by_email.items():
        existing = existing_by_email.get(email)
        if existing is None:
            to_add.append(sheet_row)
        elif existing.role == "student" and (
            existing.name != sheet_row["name"] or existing.class_group != sheet_row["class_group"]
        ):
            to_update.append({"entry": existing, "sheet_row": sheet_row})
        # else: already present as a non-student, or a student with no changes — left untouched.

    to_remove: list[WhitelistEntry] = [
        entry
        for entry in existing_all
        if entry.role == "student"
        and entry.email not in by_email
        and entry.class_group != PROTECTED_CLASS_GROUP
        and entry.email != acting_admin_email
    ]

    return to_add, to_update, to_remove


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
    current_user: User = Depends(require_admin_role),
):
    entry = db.query(WhitelistEntry).filter(WhitelistEntry.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    # Prevent an admin from removing their own access (frontend guard is bypassable).
    if entry.email == current_user.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot remove your own account.",
        )
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


@router.post("/upload", response_model=UploadPreviewResponse)
async def preview_student_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_role),
):
    """Dry run: parses the sheet and reports what an upload would add, update,
    and remove, without writing anything to the database. The frontend shows
    this as a confirmation step before calling /whitelist/upload/confirm."""
    try:
        contents = await file.read()
        students = parse_students_from_excel(contents, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    failed = []
    valid_students = []
    for idx, student in enumerate(students):
        if not student.get("email"):
            failed.append({"email": f"row {idx}", "reason": "missing email"})
            continue
        valid_students.append(student)

    # A zero-row parse almost always means a wrong/corrupt file, not a genuine
    # empty roster. Reject it rather than proposing to remove every student.
    if not valid_students:
        raise HTTPException(
            status_code=400,
            detail="No student rows could be read from this file. Please check the file and try again.",
        )

    to_add, to_update, to_remove = _build_upload_diff(db, valid_students, current_user.email)

    return {
        "to_add": [
            UploadAddition(email=s["email"], name=s["name"], class_group=s["class_group"])
            for s in to_add
        ],
        "to_update": [
            UploadUpdate(
                id=pair["entry"].id,
                email=pair["entry"].email,
                old_name=pair["entry"].name,
                new_name=pair["sheet_row"]["name"],
                old_class_group=pair["entry"].class_group,
                new_class_group=pair["sheet_row"]["class_group"],
            )
            for pair in to_update
        ],
        "to_remove": [
            UploadRemoval(id=e.id, email=e.email, name=e.name, class_group=e.class_group)
            for e in to_remove
        ],
        "failed": failed,
        "students": valid_students,
    }


@router.post("/upload/confirm", response_model=UploadConfirmResponse)
def confirm_student_upload(
    request: UploadConfirmRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_role),
):
    """Applies the change set from a previewed upload. Re-derives the diff
    server-side from the echoed sheet rows rather than trusting any
    classification the client sent, so a stale/tampered payload can't sneak
    through an unintended add/update/removal (e.g. of a TEST-group entry)."""
    students = [s.model_dump() for s in request.students]

    # Mirror the preview guard: an empty roster would classify every existing
    # student as a removal, so refuse it rather than risk a mass delete.
    if not students:
        raise HTTPException(
            status_code=400,
            detail="No student rows were provided.",
        )

    to_add, to_update, to_remove = _build_upload_diff(db, students, current_user.email)

    imported = 0
    updated = 0
    removed = 0
    failed = []

    for sheet_row in to_add:
        try:
            entry = WhitelistEntry(
                email=sheet_row["email"],
                role="student",
                name=sheet_row["name"],
                class_group=sheet_row["class_group"],
            )
            db.add(entry)

            # Sync to existing user if they have already signed in before
            user_db = db.query(User).filter(User.email == sheet_row["email"]).first()
            if user_db:
                user_db.role = "student"
                user_db.name = sheet_row["name"]
                user_db.class_group = sheet_row["class_group"]

            db.commit()
            imported += 1
        except Exception as e:
            db.rollback()
            failed.append({"email": sheet_row.get("email", "unknown"), "reason": str(e)})

    for pair in to_update:
        try:
            entry = pair["entry"]
            sheet_row = pair["sheet_row"]
            entry.name = sheet_row["name"]
            entry.class_group = sheet_row["class_group"]

            user_db = db.query(User).filter(User.email == entry.email).first()
            if user_db:
                user_db.name = sheet_row["name"]
                user_db.class_group = sheet_row["class_group"]

            db.commit()
            updated += 1
        except Exception as e:
            db.rollback()
            failed.append({"email": pair["entry"].email, "reason": str(e)})

    if request.confirm_removals:
        for entry in to_remove:
            try:
                db.delete(entry)
                db.commit()
                removed += 1
            except Exception as e:
                db.rollback()
                failed.append({"email": entry.email, "reason": str(e)})

    return {
        "imported": imported,
        "updated": updated,
        "removed": removed,
        "failed": failed,
    }

