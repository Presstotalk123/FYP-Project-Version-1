from sqlalchemy.orm import Session
from app.models.lab_item import LabItem
from app.models.lab import Lab


def labs_referencing(db: Session, kind: str, ref_id: int) -> list[str]:
    """Titles of non-deleted labs whose items reference this pool question."""
    rows = (db.query(Lab.title)
            .join(LabItem, LabItem.lab_id == Lab.id)
            .filter(LabItem.kind == kind, LabItem.ref_id == ref_id,
                    LabItem.is_deleted == 0, Lab.is_deleted == 0)
            .distinct().all())
    return [r[0] for r in rows]


def running_labs_referencing(db: Session, kind: str, ref_id: int) -> list[str]:
    """Titles of RUNNING labs whose items reference this pool question."""
    rows = (db.query(Lab.title)
            .join(LabItem, LabItem.lab_id == Lab.id)
            .filter(LabItem.kind == kind, LabItem.ref_id == ref_id,
                    LabItem.is_deleted == 0, Lab.is_deleted == 0, Lab.is_running == 1)
            .distinct().all())
    return [r[0] for r in rows]
