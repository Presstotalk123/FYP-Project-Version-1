"""Question ownership, visibility, approval, and engine input snapshots."""
from datetime import datetime, timezone

from fastapi import HTTPException

from app.config import settings
from app.core.normalization.fd_engine import FD, FDValidationError, validate_approved_answer
from app.core.normalization.fd_exercises import BusinessStatement, FDExercise
from app.models.normalization import NormalizationQuestion
from app.models.user import UserRole
from app.services.assessment_gateway import as_utc


CONTENT_FIELDS = ("title", "difficulty", "scenario", "relation_name", "attributes", "statements",
                  "sample_rows", "target_normal_form", "approved_fds", "semantic_judge_enabled", "hide_correctness")


def authoring_values(payload):
    values = payload.model_dump(exclude={"version"})
    # The project stores flags as integers. PostgreSQL does not implicitly cast
    # Python booleans bound by psycopg2 into integer columns, unlike SQLite.
    for field in ("semantic_judge_enabled", "hide_correctness"):
        values[field] = int(values[field])
    return values


def is_staff(user):
    return user.role in {UserRole.STAFF, UserRole.ADMIN}


def semantic_ready():
    return bool(settings.NORMALIZATION_SEMANTIC_API_KEY.strip() and settings.NORMALIZATION_SEMANTIC_MODEL.strip())


def snapshot(question):
    from app.core.normalization.engine import NORMALIZATION_ENGINE_VERSION
    from app.services.normalization.fd_service import ENGINE_VERSION
    return {**{key: getattr(question, key) for key in CONTENT_FIELDS},
            "id": question.id, "version": question.version,
            "semantic_judge_enabled": bool(question.semantic_judge_enabled), "hide_correctness": bool(question.hide_correctness),
            "engine_versions": {"fd": ENGINE_VERSION, "normalization": NORMALIZATION_ENGINE_VERSION}}


def exercise(data):
    return FDExercise(
        id=str(data["id"]), version=str(data["version"]), model_answer_version=str(data["version"]),
        title=data["title"], scenario=data["scenario"], relation_name=data["relation_name"],
        attributes=tuple(data["attributes"]),
        statements=tuple(BusinessStatement(**s) for s in data["statements"]),
        sample_rows=tuple(data["sample_rows"]),
        approved_model_fds=tuple(FD(frozenset(f["lhs"]), frozenset(f["rhs"])) for f in data["approved_fds"]),
    )


def validate_reference(question):
    try:
        validate_approved_answer(
            attributes=frozenset(question.attributes),
            approved=tuple(FD(frozenset(f["lhs"]), frozenset(f["rhs"])) for f in question.approved_fds),
            sample_rows=question.sample_rows,
        )
    except FDValidationError as error:
        raise HTTPException(422, str(error)) from error


def approve(question, user):
    validate_reference(question)
    if question.semantic_judge_enabled and not semantic_ready():
        raise HTTPException(422, "Configure the normalization semantic provider before publishing with AI enabled.")
    question.approved_by = user.id
    question.approved_at = datetime.now(timezone.utc)


def get_question(db, question_id, user, *, history=False):
    question = db.get(NormalizationQuestion, question_id)
    if question is None:
        raise HTTPException(404, "Question not found")
    if is_staff(user):
        if question.is_deleted and not history:
            raise HTTPException(404, "Question not found")
        return question
    if history:
        return question  # Submission ownership is checked by the history caller.
    if question.is_deleted:
        raise HTTPException(404, "Question not found")
    if question.owner_assessment_id is not None:
        from app.services.normalization.assessment import guard_access
        guard_access(db, question, user)
    elif not question.is_published:
        raise HTTPException(404, "Question not found")
    return question


def public_question(question):
    return {"id": question.id, "version": str(question.version),
            "created_by": question.created_by, "created_at": as_utc(question.created_at),
            **{key: getattr(question, key) for key in (
                "title", "difficulty", "scenario", "relation_name", "attributes", "statements",
                "sample_rows", "target_normal_form")},
            "is_published": bool(question.is_published), "hide_correctness": bool(question.hide_correctness),
            "semantic_judge_enabled": bool(question.semantic_judge_enabled)}
