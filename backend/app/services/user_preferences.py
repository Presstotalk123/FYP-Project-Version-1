"""Read and write a user's own UI preferences (see models/user_preference.py).

All SQL for the feature lives here; the endpoints stay thin, as with er_drafts.
"""
from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.user_preference import UserPreference

# The whole vocabulary. Adding a "don't show again" for another guide is one
# entry here plus the frontend key — no schema change. Kept closed so the
# table cannot quietly become a general-purpose dumping ground.
ERD_GUIDE_DISMISSED = "erd_guide_dismissed"

ALLOWED_KEYS = frozenset({ERD_GUIDE_DISMISSED})

MAX_VALUE_LENGTH = 200


def get_all(db: Session, *, user_id: int) -> dict[str, str]:
    rows = (
        db.query(UserPreference.key, UserPreference.value)
        .filter(UserPreference.user_id == user_id)
        .all()
    )
    return {row.key: row.value for row in rows}


def set_value(db: Session, *, user_id: int, key: str, value: str) -> None:
    """Upsert one preference. Raises ValueError for a key outside ALLOWED_KEYS.

    One statement rather than SELECT-then-UPDATE, as in er_drafts.save_draft:
    no read-modify-write race between two tabs, and `updated_at` set
    explicitly because `onupdate` does not fire for ON CONFLICT DO UPDATE.
    """
    if key not in ALLOWED_KEYS:
        raise ValueError(f"unknown preference key: {key!r}")

    table = UserPreference.__table__
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert

    stmt = (
        insert(table)
        .values(user_id=user_id, key=key, value=value)
        .on_conflict_do_update(
            index_elements=[table.c.user_id, table.c.key],
            set_={"value": value, "updated_at": func.now()},
        )
    )
    db.execute(stmt)
    db.commit()
