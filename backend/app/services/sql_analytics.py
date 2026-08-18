"""On-demand staff analytics over SQL-question attempts. Mirrors er_analytics.py:
no rollup tables, computed live and wrapped in the SQL_ANALYTICS cache namespace at
the endpoint. Class sizes are small; staff want fresh numbers."""
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from app.models.attempt import Attempt
from app.models.progress import UserProgress
from app.models.query_review import QueryReview
from app.models.question import Question
from app.models.tutor_chat_conversation import TutorChatConversation
from app.models.tutor_chat_message import TutorChatMessage
from app.models.user import User
from app.services.tutor_chat import persistence as tutor_persistence


def _queries_to_correct(attempt_rows: list, completed: bool, attempts_count: int) -> Optional[int]:
    """Number of queries a student ran up to & including their first correct one.

    Prefers the exact count from the attempts rows (full history is retained now
    that pruning is removed); falls back to UserProgress.attempts_count for legacy
    students whose correct attempt predates this change and was pruned away."""
    if not completed:
        return None
    for idx, a in enumerate(attempt_rows):
        if a.is_correct == 1:
            return idx + 1
    # Completed but no correct row visible (legacy pruned history) → best estimate.
    return attempts_count or None


def _chatbot_user_ids(db: Session, question_id: int) -> set:
    """Distinct students who exchanged at least one message with the tutor on this question."""
    rows = (
        db.query(TutorChatConversation.user_id)
        .join(TutorChatMessage,
              TutorChatMessage.conversation_id == TutorChatConversation.id)
        .filter(TutorChatConversation.context_type == "question",
                TutorChatConversation.question_id == question_id)
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def question_analytics(
    db: Session, question_id: int, class_group: Optional[str] = None
) -> Optional[dict]:
    question = db.query(Question).filter(Question.id == question_id).first()
    if question is None:
        return None

    progress_q = db.query(UserProgress).filter(UserProgress.question_id == question_id)
    if class_group is not None:
        progress_q = progress_q.join(User, User.id == UserProgress.user_id).filter(
            User.class_group == class_group
        )
    progress_rows = progress_q.all()
    user_ids = [p.user_id for p in progress_rows]

    # All attempts for these students on this question, grouped and chronological.
    attempts_by_user: dict[int, list] = defaultdict(list)
    if user_ids:
        attempt_rows = (
            db.query(Attempt)
            .filter(Attempt.question_id == question_id,
                    Attempt.user_id.in_(user_ids))
            .order_by(Attempt.submitted_at.asc(), Attempt.id.asc())
            .all()
        )
        for a in attempt_rows:
            attempts_by_user[a.user_id].append(a)

    chatbot_ids = _chatbot_user_ids(db, question_id)

    user_meta = {
        uid: {"email": email, "name": name, "class_group": group}
        for uid, email, name, group in (
            db.query(User.id, User.email, User.name, User.class_group)
            .filter(User.id.in_(user_ids)).all()
        )
    } if user_ids else {}

    students = []
    q_to_correct: list[int] = []
    for p in progress_rows:
        completed = bool(p.completed)
        qtc = _queries_to_correct(attempts_by_user.get(p.user_id, []), completed, p.attempts_count)
        if completed and qtc is not None:
            q_to_correct.append(qtc)
        meta = user_meta.get(p.user_id, {})
        students.append({
            "user_id": p.user_id,
            "email": meta.get("email", ""),
            "name": meta.get("name"),
            "class_group": meta.get("class_group"),
            "attempts_count": p.attempts_count,
            "completed": completed,
            "queries_to_correct": qtc,
            "used_chatbot": p.user_id in chatbot_ids,
            "last_attempted_at": p.last_attempted_at.isoformat() if p.last_attempted_at else None,
        })
    students.sort(key=lambda s: s["email"] or "")

    return {
        "question_id": question.id,
        "title": question.title,
        "student_count": len(progress_rows),
        "completed_count": sum(1 for s in students if s["completed"]),
        "avg_queries_to_correct": round(sum(q_to_correct) / len(q_to_correct), 1) if q_to_correct else None,
        "chatbot_student_count": len(chatbot_ids & set(user_ids)) if class_group else len(chatbot_ids),
        "students": students,
    }


def student_detail(db: Session, question_id: int, student_id: int) -> dict:
    attempts = (
        db.query(Attempt)
        .filter(Attempt.question_id == question_id, Attempt.user_id == student_id)
        .order_by(Attempt.submitted_at.asc(), Attempt.id.asc())
        .all()
    )
    query_history = [{
        "id": a.id,
        "query": a.query,
        "is_correct": bool(a.is_correct),
        "error_message": a.error_message,
        "execution_time_ms": a.execution_time_ms,
        "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
    } for a in attempts]

    conv = tutor_persistence.find_question_conversation(
        db, user_id=student_id, question_id=question_id
    )
    chatbot = [{
        "role": m.role,
        "content": m.content or "",
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in (tutor_persistence.transcript(db, conv) if conv else [])]

    reviews = (
        db.query(QueryReview)
        .filter(QueryReview.context_type == "question",
                QueryReview.question_id == question_id,
                QueryReview.user_id == student_id)
        .order_by(QueryReview.created_at.asc(), QueryReview.id.asc())
        .all()
    )
    review_history = [{
        "id": r.id,
        "student_query": r.student_query,
        "problem_token": r.problem_token,
        "explanation": r.explanation,
        "hint": r.hint,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in reviews]

    return {
        "student_id": student_id,
        "query_history": query_history,
        "chatbot": chatbot,
        "review_history": review_history,
    }
