from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base

# Import FK-target models so their tables are registered on Base.metadata
# (required for create_all / FK resolution when this model is imported directly,
# as the migration script does). Mirrors er_diagram_draft.py.
from app.models import user as _user  # noqa: F401
from app.models import er_diagram_question as _question  # noqa: F401


class ErDiagramImageDraft(Base):
    """A student's in-progress *uploaded image* answer for one ER question.

    The image sibling of ErDiagramDraft (which holds the draw.io XML). One
    mutable row per (user, question), overwritten in place — not an audit
    record. The bytes live in the ER storage provider (local disk / Azure);
    only the ``storage_key`` and enough metadata to rebuild a File on the
    client are kept here, exactly as er_submissions keeps
    ``submitted_image_storage_key`` rather than the blob.

    What was actually graded still lives in er_submissions (append-only); this
    is just the resumable draft the workspace restores and the finalize sweep
    grades. Exactly one index, the composite unique below: it is both the upsert
    target and the only lookup this feature performs.
    """

    __tablename__ = "er_diagram_image_drafts"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "er_diagram_question_id", name="uq_er_image_draft_user_question"
        ),
    )

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    er_diagram_question_id = Column(
        Integer, ForeignKey("er_diagram_questions.id"), nullable=False
    )
    # Server-generated UUID filename returned by the storage provider's save().
    storage_key = Column(String(255), nullable=False)
    # Kept so the client can rebuild a faithful File on restore (name shown in
    # the dropzone, correct MIME on the reconstructed blob).
    filename = Column(String(255), nullable=True)
    content_type = Column(String(128), nullable=True)
    # Bumped by the upsert, never read-modify-written. The client compares this
    # against the revision its local cache last synced to decide whether the
    # server copy is newer than what IndexedDB already holds.
    revision = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
