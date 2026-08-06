"""Admin-tunable application settings.

Reads are open to any authenticated user, because the UI has to know whether to
offer an action before the user attempts it. Writes are staff/admin only.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.models.user import User
from app.services import app_settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


class ErdSettings(BaseModel):
    student_authoring_enabled: bool


@router.get("/erd", response_model=ErdSettings)
def get_erd_settings(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return ErdSettings(
        student_authoring_enabled=settings_service.get_bool(
            db, settings_service.ERD_STUDENT_AUTHORING
        )
    )


@router.put("/erd", response_model=ErdSettings)
def update_erd_settings(
    body: ErdSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff_role),
):
    settings_service.set_bool(
        db,
        settings_service.ERD_STUDENT_AUTHORING,
        body.student_authoring_enabled,
        updated_by=current_user.id,
    )
    return body
