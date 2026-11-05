"""The normalization adapter for the shared assessment lifecycle."""
from copy import deepcopy
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func

from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.models.normalization import NormalizationQuestion, NormalizationSubmission, NormalizationReview
from app.services.assessment_gateway import resolve_state
from app.services.assessment_timer import enforce_not_expired
from app.services.normalization.questions import CONTENT_FIELDS

ITEM_TYPE = "normalization_question"


def guard_access(db, question, user, *, lock=False):
    assessment = db.get(Assessment, question.owner_assessment_id)
    if not assessment or assessment.is_deleted or not assessment.is_published:
        raise HTTPException(404, "Question not found")
    if not db.query(AssessmentItem.id).filter_by(assessment_id=assessment.id, item_type=ITEM_TYPE, item_id=question.id).first():
        raise HTTPException(404, "Question not found")
    session = db.query(AssessmentSession).filter_by(assessment_id=assessment.id, user_id=user.id, is_active=1).first()
    if session is None:
        raise HTTPException(403, "Assessment has ended.")
    if lock:
        # UPDATE is also a write lock on SQLite, where SELECT FOR UPDATE is ignored.
        db.query(AssessmentSession).filter_by(id=session.id).update(
            {AssessmentSession.is_active: AssessmentSession.is_active}, synchronize_session=False)
        db.refresh(session)
    if not session.is_active or session.attempt_complete:
        raise HTTPException(403, "Assessment has ended.")
    enforce_not_expired(db, session)
    if not (resolve_state(db, assessment, user).is_open if assessment.gateway_enabled else assessment.is_running):
        raise HTTPException(403, "Assessment has ended.")
    return session


def clone_for_assessment(db, question_id, assessment_id, hide_correctness=0):
    from app.services.assessment_clone import AssessmentCloneError
    from app.services.normalization.questions import validate_reference, semantic_ready
    master = db.get(NormalizationQuestion, question_id)
    if not master or master.is_deleted or master.owner_assessment_id is not None:
        raise AssessmentCloneError("Normalization bank question not found")
    validate_reference(master)
    if master.semantic_judge_enabled and not semantic_ready():
        raise AssessmentCloneError("Normalization semantic provider is not configured")
    fields = {key: deepcopy(getattr(master, key)) for key in CONTENT_FIELDS}
    fields["hide_correctness"] = hide_correctness
    clone = NormalizationQuestion(**fields, created_by=master.created_by, version=master.version,
                                  approved_by=master.approved_by or db.get(Assessment, assessment_id).created_by,
                                  approved_at=master.approved_at or datetime.now(timezone.utc),
                                  owner_assessment_id=assessment_id, is_published=0, is_deleted=0)
    db.add(clone)
    db.flush()
    return clone.id


def delete_clones(db, assessment_id):
    db.query(NormalizationQuestion).filter_by(owner_assessment_id=assessment_id).update(
        {NormalizationQuestion.is_deleted: 1}, synchronize_session=False)


def reset_student(db, student_id, question_id, assessment_id):
    q = db.get(NormalizationQuestion, question_id)
    if not q or q.owner_assessment_id != assessment_id:
        return 0
    ids = db.query(NormalizationSubmission.id).filter_by(user_id=student_id, question_id=question_id)
    db.query(NormalizationReview).filter(NormalizationReview.submission_id.in_(ids)).delete(synchronize_session=False)
    return db.query(NormalizationSubmission).filter_by(user_id=student_id, question_id=question_id).delete(synchronize_session=False)


def scores(db, user_ids, question_ids):
    if not user_ids or not question_ids:
        return {}, {}, set()
    rows = db.query(NormalizationSubmission.user_id, NormalizationSubmission.question_id,
                    func.max(NormalizationSubmission.overall_percent), func.count(NormalizationSubmission.id)).filter(
        NormalizationSubmission.user_id.in_(user_ids), NormalizationSubmission.question_id.in_(question_ids)
    ).group_by(NormalizationSubmission.user_id, NormalizationSubmission.question_id).all()
    accepted = set(db.query(NormalizationSubmission.user_id, NormalizationSubmission.question_id).filter(
        NormalizationSubmission.user_id.in_(user_ids), NormalizationSubmission.question_id.in_(question_ids),
        NormalizationSubmission.decision == "accepted").distinct().all())
    return ({(u, q): (score or 0) / 100 for u, q, score, count in rows},
            {(u, q): count for u, q, score, count in rows}, accepted)


def score_detail(db, question_id, user_id):
    fractions, counts, accepted = scores(db, [user_id], [question_id])
    key = (user_id, question_id)
    return fractions.get(key, 0.0), counts.get(key, 0), key in accepted


def titles(db, question_ids):
    return dict(db.query(NormalizationQuestion.id, NormalizationQuestion.title).filter(
        NormalizationQuestion.id.in_(list(question_ids))).all()) if question_ids else {}


def title(db, question_id):
    return titles(db, [question_id]).get(question_id, f"Normalization #{question_id}")


def refresh_score(db, question, user_id):
    from app.core.cache import bump_version, Ns
    from app.services.assessment_scoring import compute_weighted_score
    if question.owner_assessment_id:
        session = db.query(AssessmentSession).filter_by(assessment_id=question.owner_assessment_id, user_id=user_id).first()
        if session:
            db.query(AssessmentSession).filter_by(id=session.id).update(
                {AssessmentSession.is_active: AssessmentSession.is_active}, synchronize_session=False)
            db.refresh(session)
            if session.attempt_complete:
                session.weighted_score = compute_weighted_score(db, db.get(Assessment, question.owner_assessment_id), user_id)
    bump_version(db, Ns.ASSESSMENT_ANALYTICS)
