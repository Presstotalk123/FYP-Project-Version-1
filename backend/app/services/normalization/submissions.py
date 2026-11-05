"""Composite evaluation, durable admission, feedback visibility, and FD review."""
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import InvalidRequestError

from app.config import settings
from app.core.normalization.engine import evaluate_recursive_decomposition_process, evaluate_submission
from app.core.normalization.fd_engine import FD, FDValidationError
from app.core.normalization.schemas import SubmissionInput as EngineInput, IntegratedScoreResponse
from app.models.normalization import NormalizationSubmission, NormalizationReview
from app.services.normalization.fd_service import evaluate_fd_attempt
from app.services.normalization.integrated_workflow import build_integrated_exercise
from app.services.normalization.semantic_judge import OpenAISemanticJudge
from app.services.normalization import questions, assessment
from app.services.assessment_gateway import as_utc


def score(fd_result, result):
    checks = [result.attribute_coverage, result.lossless_join, result.relations_satisfy_target,
              result.proposed_keys_correct, bool(result.process_evaluation and result.process_evaluation.valid)]
    if result.dependency_preservation_required:
        checks.append(result.dependency_preservation)
    fd_percent = 100 if fd_result.decision == "accepted" else 0
    normalization_percent = round(100 * sum(checks) / len(checks))
    return IntegratedScoreResponse(fd_percent=fd_percent, normalization_percent=normalization_percent,
                                   overall_percent=round((fd_percent + normalization_percent) / 2))


def evaluate(submission_id, data, payload):
    source = questions.exercise(data)
    fds = [FD(frozenset(f.lhs), frozenset(f.rhs)) for f in payload.functional_dependencies]
    judge = None
    if data["semantic_judge_enabled"] and questions.semantic_ready():
        judge = OpenAISemanticJudge(api_key=settings.NORMALIZATION_SEMANTIC_API_KEY,
                                    model=settings.NORMALIZATION_SEMANTIC_MODEL)
    try:
        fd_result, semantic = evaluate_fd_attempt(attempt_id=submission_id, exercise=source,
            submitted_fds=fds, assumption=payload.assumption.strip(), semantic_judge=judge,
            semantic_review_enabled=bool(data["semantic_judge_enabled"]))
    finally:
        if judge:
            judge.close()
    context = build_integrated_exercise(source=source, submitted_fds=fds, target=data["target_normal_form"])
    process = evaluate_recursive_decomposition_process(payload.process, set(source.attributes),
        list(context.functional_dependencies), payload.relations, context.target_normal_form)
    result = evaluate_submission(submission_id, EngineInput(exercise_id=source.id,
        target_normal_form=context.target_normal_form, assumptions=payload.assumption,
        functional_dependencies=payload.functional_dependencies, relations=payload.relations),
        set(source.attributes), dependency_preservation_required=context.dependency_preservation_required,
        process_evaluation=process)
    decision = ("staff_review" if fd_result.decision == "staff_review" else
                "accepted" if fd_result.decision == "accepted" and result.meets_requirements else "rejected")
    return {"submission_id": submission_id, "decision": decision,
            "score": score(fd_result, result).model_dump(), "fd_evaluation": fd_result.model_dump(mode="json"),
            "normalization_evaluation": result.model_dump(mode="json")}, semantic


def validate_payload(question, payload):
    if payload.exercise_version != str(question.version):
        raise HTTPException(409, "This question changed. Reload before submitting.")
    if payload.target_normal_form != question.target_normal_form:
        raise HTTPException(422, "The target normal form is assigned by staff.")
    domain = set(question.attributes)
    nodes = [payload.process.root] + [c for s in payload.process.steps for c in s.children]
    for relation in [*nodes, *payload.relations]:
        if not set(relation.attributes) <= domain:
            raise HTTPException(422, "Relations contain unknown attributes.")
    for fd in [*payload.functional_dependencies, *(s.selected_fd for s in payload.process.steps)]:
        if not set(fd.lhs + fd.rhs) <= domain or len(fd.lhs + fd.rhs) > 16:
            raise HTTPException(422, "Dependencies contain unknown or excessive attributes.")
    if len(payload.model_dump_json()) > 1_000_000:
        raise HTTPException(413, "Submission is too large.")


def hidden(question, user):
    return bool(question.hide_correctness) and not questions.is_staff(user)


def view(db, row, question, user):
    result = deepcopy(row.original_result)
    if result and row.review_version:
        result["decision"] = row.decision
        result["score"]["fd_percent"] = row.fd_percent
        result["score"]["overall_percent"] = row.overall_percent
        result["fd_evaluation"].update(decision="accepted" if row.fd_percent == 100 else "rejected",
            can_proceed=row.fd_percent == 100, decision_source="staff_review",
            feedback="Staff have reviewed this FD interpretation.")
    reviews = db.query(NormalizationReview).filter_by(submission_id=row.id).order_by(NormalizationReview.id).all()
    hide = hidden(question, user)
    output = {"id": row.id, "question_id": row.question_id, "user_id": row.user_id,
              "question_version": row.question_version, "created_at": as_utc(row.created_at),
              "payload": row.payload, "status": "submitted" if hide else row.status,
              "feedback_hidden": hide, "result": None if hide else result,
              "review_version": 0 if hide else row.review_version,
              "reviews": [] if hide else [{"id": r.id, "actor_id": r.actor_id, "decision": r.decision,
                  "reason": r.reason, "created_at": as_utc(r.created_at)} for r in reviews]}
    if questions.is_staff(user):
        output.update(original_result=row.original_result, snapshot=row.snapshot, semantic_evidence=row.semantic_evidence)
    return output


def submit(db, question, user, payload):
    key = str(payload.request_key)
    previous = db.query(NormalizationSubmission).filter_by(user_id=user.id, request_key=key).first()
    if previous:
        if previous.question_id != question.id or previous.payload != payload.model_dump(mode="json"):
            raise HTTPException(409, "This request key was already used for a different submission.")
        return previous
    validate_payload(question, payload)
    assessment_session = None
    if question.owner_assessment_id and not questions.is_staff(user):
        assessment_session = assessment.guard_access(db, question, user, lock=True)
    started = datetime.now(timezone.utc)
    row = NormalizationSubmission(id=str(uuid4()), request_key=key, question_id=question.id, user_id=user.id,
        question_version=question.version, snapshot=questions.snapshot(question), payload=payload.model_dump(mode="json"))
    row_id = row.id
    data = deepcopy(row.snapshot)
    db.add(row)
    try:
        db.commit()  # Admit durably before provider latency; no database lock spans the call.
    except IntegrityError:
        db.rollback()
        previous = db.query(NormalizationSubmission).filter_by(user_id=user.id, request_key=key).first()
        if previous is None or previous.question_id != question.id or previous.payload != payload.model_dump(mode="json"):
            raise HTTPException(409, "Submission request conflict")
        return previous
    db.rollback()  # Release the read transaction too; semantic calls do not occupy DB locks.
    try:
        result, semantic = evaluate(row_id, data, payload)
    except FDValidationError as error:
        row = db.get(NormalizationSubmission, row_id)
        if row:
            row.status = "failed"
            db.commit()
        raise HTTPException(422, str(error)) from error
    except Exception:
        row = db.get(NormalizationSubmission, row_id)
        if row:
            row.status = "failed"
            db.commit()
        raise
    row = db.get(NormalizationSubmission, row_id)
    if row is None:  # A staff reset may have removed an in-flight attempt.
        raise HTTPException(409, "This attempt was reset while grading.")
    row.original_result = result
    row.semantic_evidence = semantic.model_dump(mode="json") if semantic else None
    row.status = "completed"
    row.fd_percent = result["score"]["fd_percent"]
    row.normalization_percent = result["score"]["normalization_percent"]
    row.overall_percent = result["score"]["overall_percent"]
    row.decision = result["decision"]
    db.flush()
    assessment.refresh_score(db, question, user.id)
    db.flush()  # Persist the recomputed total before refreshing the timer's ORM instance.
    if assessment_session:
        db.refresh(assessment_session)
        if assessment_session.is_active and assessment_session.end_time:
            assessment_session.end_time += datetime.now(timezone.utc) - started
    db.commit()
    try:
        db.refresh(row)
    except InvalidRequestError as error:
        raise HTTPException(409, "This attempt was reset while grading.") from error
    return row


def review(db, row, question, user, payload):
    if row.original_result is None:
        raise HTTPException(409, "This attempt has not finished grading.")
    if not payload.reason.strip():
        raise HTTPException(422, "A review reason is required.")
    original_fd = row.original_result["fd_evaluation"]
    if payload.decision == "accepted" and (
        original_fd["formal_evidence"]["sample_contradictions"] or original_fd["decision_source"] == "trivial_only"
    ):
        raise HTTPException(422, "A semantic interpretation cannot override a sample contradiction or a trivial-only FD set.")
    changed = db.query(NormalizationSubmission).filter_by(id=row.id, review_version=payload.version).update(
        {NormalizationSubmission.review_version: payload.version + 1}, synchronize_session=False)
    if not changed:
        raise HTTPException(409, "Another staff member reviewed this attempt. Reload first.")
    db.refresh(row)
    row.fd_percent = 100 if payload.decision == "accepted" else 0
    row.overall_percent = round((row.fd_percent + row.normalization_percent) / 2)
    formal_pass = row.original_result["normalization_evaluation"]["meets_requirements"]
    row.decision = "accepted" if row.fd_percent == 100 and formal_pass else "rejected"
    db.add(NormalizationReview(submission_id=row.id, actor_id=user.id,
                              decision=payload.decision, reason=payload.reason.strip()))
    db.flush()
    assessment.refresh_score(db, question, row.user_id)
    db.commit()
