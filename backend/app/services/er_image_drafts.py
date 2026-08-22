"""Read and write the student's in-progress *uploaded image* answer.

The image sibling of er_drafts.py. All SQL for the image-draft feature lives
here; the endpoints stay thin. The bytes are stored in the ER storage provider
(local disk / Azure) — this module only manages the row that points at them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.er_diagram_image_draft import ErDiagramImageDraft


def get_image_draft(
    db: Session, *, user_id: int, question_id: int
) -> Optional[ErDiagramImageDraft]:
    return (
        db.query(ErDiagramImageDraft)
        .filter(
            ErDiagramImageDraft.user_id == user_id,
            ErDiagramImageDraft.er_diagram_question_id == question_id,
        )
        .first()
    )


def save_image_draft(
    db: Session,
    *,
    user_id: int,
    question_id: int,
    storage_key: str,
    filename: Optional[str],
    content_type: Optional[str],
) -> tuple[int, datetime, Optional[str]]:
    """Upsert the image draft; return ``(revision, updated_at, superseded_key)``.

    ``superseded_key`` is the ``storage_key`` this upsert replaced (None on a
    first insert) so the caller can delete the now-orphaned blob from storage —
    the row only ever points at one image, and the old bytes are dead once the
    row moves on. Read it BEFORE the upsert (one small query) because the upsert
    overwrites the column in place; a fresh insert simply finds nothing.

    One statement for the write itself rather than SELECT-then-UPDATE: no
    read-modify-write race between two tabs of the same student, and ``revision``
    is incremented SQL-side. ``updated_at`` is set explicitly because
    SQLAlchemy's ``onupdate`` hook does not fire for an ON CONFLICT DO UPDATE.
    """
    existing = get_image_draft(db, user_id=user_id, question_id=question_id)
    superseded_key = existing.storage_key if existing is not None else None

    table = ErDiagramImageDraft.__table__
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert

    stmt = (
        insert(table)
        .values(
            user_id=user_id,
            er_diagram_question_id=question_id,
            storage_key=storage_key,
            filename=filename,
            content_type=content_type,
            revision=1,
        )
        .on_conflict_do_update(
            index_elements=[table.c.user_id, table.c.er_diagram_question_id],
            set_={
                "storage_key": storage_key,
                "filename": filename,
                "content_type": content_type,
                "revision": table.c.revision + 1,
                "updated_at": func.now(),
            },
        )
        .returning(table.c.revision, table.c.updated_at)
    )

    row = db.execute(stmt).one()
    db.commit()
    # The replaced blob (if any) is now unreferenced; caller deletes it. Never
    # return the same key we just wrote — an unchanged re-save of identical bytes
    # goes through save() with a NEW uuid key, so superseded_key != storage_key.
    return int(row.revision), row.updated_at, superseded_key


def delete_image_draft(
    db: Session, *, user_id: int, question_id: int
) -> Optional[str]:
    """Delete the draft row; return its ``storage_key`` so the caller can remove
    the blob. Returns None when there was no draft to delete.
    """
    existing = get_image_draft(db, user_id=user_id, question_id=question_id)
    if existing is None:
        return None
    storage_key = existing.storage_key
    db.delete(existing)
    db.commit()
    return storage_key
