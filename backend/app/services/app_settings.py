"""Read and write admin-tunable settings.

Defaults live here, in code, so a missing row is a well-defined state rather
than a bug. Callers never see None.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

#: Students may author their own ERD questions. Off unless staff turn it on.
ERD_STUDENT_AUTHORING = "erd.student_authoring_enabled"

DEFAULTS: dict[str, bool] = {
    ERD_STUDENT_AUTHORING: False,
}

_TRUE = {"1", "true", "yes", "on"}


def get_bool(db: Session, key: str) -> bool:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        return DEFAULTS.get(key, False)
    return str(row.value).strip().lower() in _TRUE


def set_bool(db: Session, key: str, value: bool, *, updated_by: Optional[int] = None) -> bool:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        row = AppSetting(key=key, value="true" if value else "false", updated_by=updated_by)
        db.add(row)
    else:
        row.value = "true" if value else "false"
        row.updated_by = updated_by
    db.commit()
    return value
