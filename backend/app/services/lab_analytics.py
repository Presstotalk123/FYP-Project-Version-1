"""On-demand staff analytics over Lab attempts/submissions. Mirrors er_analytics.py:
computed live, wrapped in the LAB_ANALYTICS cache namespace at the endpoint."""
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session

from app.models.lab import Lab
from app.models.lab_attempt import LabAttempt
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.query_review import QueryReview
from app.models.tutor_chat_conversation import TutorChatConversation
from app.models.tutor_chat_message import TutorChatMessage
from app.models.user import User


def _submissions_to_correct(sub_rows: list) -> Optional[int]:
    """Number of task submissions a student made up to & including their first correct
    one. Lab submissions are never pruned, so this is always exact. None if unsolved."""
    for idx, s in enumerate(sub_rows):
        if s.is_correct == 1:
            return idx + 1
    return None


def _chatbot_user_ids(db: Session, lab_id: int) -> set:
    """Distinct students who exchanged at least one message with the tutor on this lab."""
    rows = (
        db.query(TutorChatConversation.user_id)
        .join(TutorChatMessage,
              TutorChatMessage.conversation_id == TutorChatConversation.id)
        .filter(TutorChatConversation.context_type == "lab",
                TutorChatConversation.lab_id == lab_id)
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def lab_analytics(
    db: Session, lab_id: int, class_group: Optional[str] = None
) -> Optional[dict]:
    lab = db.query(Lab).filter(Lab.id == lab_id, Lab.is_deleted == 0).first()
    if lab is None:
        return None

    tasks = (
        db.query(LabTask)
        .filter(LabTask.lab_id == lab_id, LabTask.is_deleted == 0)
        .order_by(LabTask.order_index.asc())
        .all()
    )

    # Class-group filter → restrict to those users.
    allowed_ids: Optional[set] = None
    if class_group is not None:
        allowed_ids = {
            r[0] for r in db.query(User.id).filter(User.class_group == class_group).all()
        }

    # All task submissions for the lab, chronological, grouped by (user, task).
    sub_q = db.query(LabTaskSubmission).filter(LabTaskSubmission.lab_id == lab_id)
    submissions = sub_q.order_by(
        LabTaskSubmission.submitted_at.asc(), LabTaskSubmission.id.asc()
    ).all()
    if allowed_ids is not None:
        submissions = [s for s in submissions if s.user_id in allowed_ids]

    by_user_task: dict[tuple, list] = defaultdict(list)
    tasks_correct_by_user: dict[int, set] = defaultdict(set)
    last_submission_by_user: dict[int, object] = {}
    attempted_user_ids: set = set()
    for s in submissions:
        by_user_task[(s.user_id, s.task_id)].append(s)
        attempted_user_ids.add(s.user_id)
        if s.is_correct == 1:
            tasks_correct_by_user[s.user_id].add(s.task_id)
        last_submission_by_user[s.user_id] = s.submitted_at

    # Students who ran any query also count as having attempted the lab.
    attempt_q = db.query(LabAttempt.user_id).filter(LabAttempt.lab_id == lab_id).distinct()
    for (uid,) in attempt_q.all():
        if allowed_ids is None or uid in allowed_ids:
            attempted_user_ids.add(uid)

    # Per-task mean submissions-to-correct.
    task_stats = []
    for t in tasks:
        counts = []
        solvers = 0
        task_attempters = set()
        for (uid, tid), rows in by_user_task.items():
            if tid != t.id:
                continue
            task_attempters.add(uid)
            stc = _submissions_to_correct(rows)
            if stc is not None:
                counts.append(stc)
                solvers += 1
        task_stats.append({
            "task_id": t.id,
            "title": t.title,
            "order_index": t.order_index,
            "attempted_count": len(task_attempters),
            "solved_count": solvers,
            "avg_submissions_to_correct": round(sum(counts) / len(counts), 1) if counts else None,
        })

    chatbot_ids = _chatbot_user_ids(db, lab_id)
    if allowed_ids is not None:
        chatbot_ids = chatbot_ids & allowed_ids

    user_meta = {
        uid: {"email": email, "class_group": group}
        for uid, email, group in (
            db.query(User.id, User.email, User.class_group)
            .filter(User.id.in_(attempted_user_ids)).all()
        )
    } if attempted_user_ids else {}

    students = []
    for uid in attempted_user_ids:
        meta = user_meta.get(uid, {})
        last = last_submission_by_user.get(uid)
        students.append({
            "user_id": uid,
            "email": meta.get("email", ""),
            "class_group": meta.get("class_group"),
            "tasks_correct": len(tasks_correct_by_user.get(uid, set())),
            "used_chatbot": uid in chatbot_ids,
            "last_submission_at": last.isoformat() if last else None,
        })
    students.sort(key=lambda s: s["email"] or "")

    return {
        "lab_id": lab.id,
        "title": lab.title,
        "total_tasks": len(tasks),
        "student_count": len(attempted_user_ids),
        "chatbot_student_count": len(chatbot_ids),
        "tasks": task_stats,
        "students": students,
    }


def student_detail(db: Session, lab_id: int, student_id: int) -> dict:
    attempts = (
        db.query(LabAttempt)
        .filter(LabAttempt.lab_id == lab_id, LabAttempt.user_id == student_id)
        .order_by(LabAttempt.submitted_at.asc(), LabAttempt.id.asc())
        .all()
    )
    query_history = [{
        "id": a.id,
        "query": a.query,
        "success": bool(a.success),
        "error_message": a.error_message,
        "execution_time_ms": a.execution_time_ms,
        "row_count": a.row_count,
        "session_id": a.session_id,
        "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
    } for a in attempts]

    # Lab chat is keyed per session, so a student can have several conversations
    # across their runs of the lab — merge them chronologically.
    messages = (
        db.query(TutorChatMessage)
        .join(TutorChatConversation,
              TutorChatConversation.id == TutorChatMessage.conversation_id)
        .filter(TutorChatConversation.context_type == "lab",
                TutorChatConversation.lab_id == lab_id,
                TutorChatConversation.user_id == student_id)
        .order_by(TutorChatMessage.created_at.asc(), TutorChatMessage.id.asc())
        .all()
    )
    chatbot = [{
        "role": m.role,
        "content": m.content or "",
        "created_at": m.created_at.isoformat() if m.created_at else None,
    } for m in messages]

    reviews = (
        db.query(QueryReview)
        .filter(QueryReview.context_type == "lab",
                QueryReview.lab_id == lab_id,
                QueryReview.user_id == student_id)
        .order_by(QueryReview.created_at.asc(), QueryReview.id.asc())
        .all()
    )
    review_history = [{
        "id": r.id,
        "task_id": r.task_id,
        "student_query": r.student_query,
        "problem_token": r.problem_token,
        "explanation": r.explanation,
        "hint": r.hint,
        "db_state_message": r.db_state_message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in reviews]

    return {
        "student_id": student_id,
        "query_history": query_history,
        "chatbot": chatbot,
        "review_history": review_history,
    }
