"""Read and write the student's in-progress ERD canvas.

All SQL for the draft feature lives here; the endpoints stay thin, matching
er_analytics.py and assessment_scoring.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.models.er_diagram_draft import ErDiagramDraft


def get_draft(db: Session, *, user_id: int, question_id: int) -> Optional[ErDiagramDraft]:
    return (
        db.query(ErDiagramDraft)
        .filter(
            ErDiagramDraft.user_id == user_id,
            ErDiagramDraft.er_diagram_question_id == question_id,
        )
        .first()
    )


def get_draft_revision(
    db: Session, *, user_id: int, question_id: int
) -> Optional[tuple[int, datetime]]:
    """Lightweight lookup for the conditional-GET fast path: revision and
    updated_at only, never the `xml` column (up to 500 KB per row). Callers
    should use this to resolve `known_revision` hits and fall back to
    `get_draft` only when the content itself is actually needed.
    """
    row = (
        db.query(ErDiagramDraft.revision, ErDiagramDraft.updated_at)
        .filter(
            ErDiagramDraft.user_id == user_id,
            ErDiagramDraft.er_diagram_question_id == question_id,
        )
        .first()
    )
    return (row.revision, row.updated_at) if row else None


def save_draft(
    db: Session, *, user_id: int, question_id: int, xml: str
) -> tuple[int, datetime]:
    """Upsert the draft; return its new (revision, updated_at).

    One statement rather than SELECT-then-UPDATE: half the round trips, half the
    connection hold time, and no read-modify-write race between two tabs of the
    same student. `revision` is incremented SQL-side for the same reason.

    `updated_at` is set explicitly because SQLAlchemy's `onupdate` hook does not
    fire for an ON CONFLICT DO UPDATE — the column would otherwise stay frozen
    at the row's creation time.
    """
    table = ErDiagramDraft.__table__
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert

    stmt = (
        insert(table)
        .values(
            user_id=user_id,
            er_diagram_question_id=question_id,
            xml=xml,
            revision=1,
        )
        .on_conflict_do_update(
            index_elements=[table.c.user_id, table.c.er_diagram_question_id],
            set_={
                "xml": xml,
                "revision": table.c.revision + 1,
                "updated_at": func.now(),
            },
        )
        .returning(table.c.revision, table.c.updated_at)
    )

    row = db.execute(stmt).one()
    db.commit()
    return int(row.revision), row.updated_at
