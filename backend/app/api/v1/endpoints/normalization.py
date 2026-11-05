"""Normalization is an independent question type using Akela identity and assessment rules."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user, require_staff_role
from app.models.normalization import NormalizationQuestion, NormalizationSubmission, NormalizationReview
from app.models.user import User
from app.schemas.normalization import QuestionInput, SubmissionInput, ReviewInput, ReviewRequest
from app.services.normalization import questions, submissions, assessment

router = APIRouter(prefix="/normalization", tags=["normalization"])


def bank_query(db):
    return db.query(NormalizationQuestion).filter_by(is_deleted=0, owner_assessment_id=None)


def editable(db, question_id, user):
    question = questions.get_question(db, question_id, user)
    if question.owner_assessment_id is not None:
        raise HTTPException(409, "Assessment copies are frozen. Edit the bank question instead.")
    return question


def authoring(question):
    return {**questions.snapshot(question), "is_published": bool(question.is_published),
            "approved_at": question.approved_at, "created_by": question.created_by, "created_at": question.created_at}


@router.get("/capabilities")
def capabilities(user: User = Depends(require_staff_role)):
    return {"semantic_judge_configured": questions.semantic_ready()}


@router.get("/progress")
def progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    output = []
    for q in bank_query(db).filter_by(is_published=1).all():
        rows = db.query(NormalizationSubmission).filter_by(user_id=user.id, question_id=q.id,
                                                         question_version=q.version).all()
        hide = submissions.hidden(q, user)
        output.append({"question_id": q.id, "attempt_count": len(rows),
            "best_score": None if hide else max((r.overall_percent for r in rows if r.overall_percent is not None), default=None),
            "completed": False if hide else any(r.decision == "accepted" for r in rows),
            "feedback_hidden": hide, "review_pending": False if hide else any(r.decision == "staff_review" for r in rows)})
    return output


@router.get("/questions")
def list_questions(difficulty: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = bank_query(db)
    if not questions.is_staff(user):
        query = query.filter_by(is_published=1)
    if difficulty:
        query = query.filter_by(difficulty=difficulty)
    return [questions.public_question(q) for q in query.order_by(NormalizationQuestion.created_at.desc()).all()]


@router.post("/questions", status_code=201)
def create_question(payload: QuestionInput, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    q = NormalizationQuestion(**questions.authoring_values(payload), created_by=user.id)
    questions.validate_reference(q)
    db.add(q)
    db.commit()
    return authoring(q)


@router.get("/questions/{question_id}/authoring")
def get_authoring(question_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    return authoring(questions.get_question(db, question_id, user))


@router.get("/questions/{question_id}")
def get_question(question_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return questions.public_question(questions.get_question(db, question_id, user))


@router.put("/questions/{question_id}")
def update_question(question_id: int, payload: QuestionInput, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    q = editable(db, question_id, user)
    if payload.version != q.version:
        raise HTTPException(409, "Question changed. Reload before saving.")
    # Compare-and-swap protects authoring across workers, including PostgreSQL.
    changed = db.query(NormalizationQuestion).filter_by(id=q.id, version=payload.version).update(
        {NormalizationQuestion.version: payload.version + 1}, synchronize_session=False)
    if not changed:
        raise HTTPException(409, "Question changed. Reload before saving.")
    db.refresh(q)
    for field, value in questions.authoring_values(payload).items():
        setattr(q, field, value)
    questions.validate_reference(q)
    q.approved_by = None
    q.approved_at = None
    if q.is_published:
        questions.approve(q, user)
    db.commit()
    return authoring(q)


@router.delete("/questions/{question_id}", status_code=204)
def delete_question(question_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    q = editable(db, question_id, user)
    q.is_deleted = 1
    q.is_published = 0
    db.commit()


@router.post("/questions/{question_id}/publish")
def publish(question_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    q = editable(db, question_id, user)
    questions.approve(q, user)
    q.is_published = 1
    db.commit()
    return authoring(q)


@router.post("/questions/{question_id}/unpublish")
def unpublish(question_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    q = editable(db, question_id, user)
    q.is_published = 0
    db.commit()
    return authoring(q)


@router.post("/questions/{question_id}/preview")
def preview(question_id: int, payload: SubmissionInput, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    q = questions.get_question(db, question_id, user)
    submissions.validate_payload(q, payload)
    result, _ = submissions.evaluate("preview", questions.snapshot(q), payload)
    return {"id": "preview", "question_id": q.id, "user_id": user.id, "question_version": q.version,
            "payload": payload.model_dump(mode="json"), "status": "completed", "result": result,
            "feedback_hidden": False, "review_version": 0, "reviews": []}


@router.post("/questions/{question_id}/submissions")
def submit(question_id: int, payload: SubmissionInput, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if questions.is_staff(user):
        raise HTTPException(403, "Use staff preview; previews do not create student attempts.")
    # A retry can retrieve its already admitted result even after the session ended.
    previous = db.query(NormalizationSubmission).filter_by(user_id=user.id, request_key=str(payload.request_key)).first()
    if previous:
        if previous.question_id != question_id or previous.payload != payload.model_dump(mode="json"):
            raise HTTPException(409, "Submission request conflict")
        q = questions.get_question(db, question_id, user, history=True)
        return submissions.view(db, previous, q, user)
    q = questions.get_question(db, question_id, user)
    row = submissions.submit(db, q, user, payload)
    return submissions.view(db, row, q, user)


def owned_submission(db, submission_id, user):
    row = db.get(NormalizationSubmission, submission_id)
    if not row or (row.user_id != user.id and not questions.is_staff(user)):
        raise HTTPException(404, "Submission not found")
    q = questions.get_question(db, row.question_id, user, history=True)
    return row, q


@router.get("/questions/{question_id}/submissions")
def history(question_id: int, limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    rows = db.query(NormalizationSubmission).filter_by(question_id=question_id, user_id=user.id).order_by(
        NormalizationSubmission.created_at.desc()).limit(limit).all()
    q = questions.get_question(db, question_id, user, history=bool(rows))
    return [submissions.view(db, row, q, user) for row in rows]


@router.get("/submissions/{submission_id}")
def detail(submission_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row, q = owned_submission(db, submission_id, user)
    return submissions.view(db, row, q, user)


@router.post("/submissions/{submission_id}/review-request")
def request_review(submission_id: str, payload: ReviewRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    row, q = owned_submission(db, submission_id, user)
    if submissions.hidden(q, user) or not row.original_result or not payload.reason.strip():
        raise HTTPException(409, "Review is unavailable for this submission.")
    db.add(NormalizationReview(submission_id=row.id, actor_id=user.id, decision="requested", reason=payload.reason.strip()))
    db.commit()
    return submissions.view(db, row, q, user)


@router.post("/submissions/{submission_id}/review")
def review(submission_id: str, payload: ReviewInput, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    row, q = owned_submission(db, submission_id, user)
    submissions.review(db, row, q, user, payload)
    return submissions.view(db, row, q, user)


@router.get("/questions/{question_id}/analytics")
def analytics(question_id: int, class_group: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    q = questions.get_question(db, question_id, user, history=True)
    query = db.query(NormalizationSubmission).join(User, User.id == NormalizationSubmission.user_id).filter(
        NormalizationSubmission.question_id == question_id, User.role == "student")
    if class_group:
        query = query.filter(User.class_group == class_group)
    rows = query.order_by(NormalizationSubmission.created_at.desc()).all()
    users = {uid: db.get(User, uid) for uid in {r.user_id for r in rows}}
    graded = [r for r in rows if r.overall_percent is not None]
    def mean(field):
        return round(sum(getattr(r, field) for r in graded) / len(graded), 1) if graded else None
    output = []
    for row in rows:
        student = users[row.user_id]
        output.append({**submissions.view(db, row, q, user), "student_name": student.name,
                       "student_email": student.email, "class_group": student.class_group})
    return {"question": questions.public_question(q), "attempt_count": len(rows), "student_count": len(users),
            "average_fd": mean("fd_percent"), "average_normalization": mean("normalization_percent"),
            "average_score": mean("overall_percent"), "review_pending": sum(
                item["result"] is not None and (item["result"]["decision"] == "staff_review"
                or bool(item["reviews"] and item["reviews"][-1]["decision"] == "requested")) for item in output),
            "score_distribution": {f"{low}–{min(low + 24, 100)}": sum(low <= r.overall_percent <= min(low + 24, 100) for r in graded)
                                   for low in (0, 25, 50, 75, 100)}, "submissions": output}


@router.get("/questions/{question_id}/students/{student_id}/submissions")
def student_history(question_id: int, student_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff_role)):
    q = questions.get_question(db, question_id, user, history=True)
    rows = db.query(NormalizationSubmission).filter_by(question_id=question_id, user_id=student_id).order_by(
        NormalizationSubmission.created_at.desc()).all()
    return [submissions.view(db, row, q, user) for row in rows]
