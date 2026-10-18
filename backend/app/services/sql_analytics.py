"""On-demand staff analytics over SQL-question attempts. Mirrors er_analytics.py:
no rollup tables, computed live and wrapped in the SQL_ANALYTICS cache namespace at
the endpoint. Class sizes are small; staff want fresh numbers."""
from collections import defaultdict
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.attempt import Attempt
from app.models.progress import UserProgress
from app.models.query_review import QueryReview
from app.models.question import Question
from app.models.question_concept import QuestionConcept
from app.models.sql_concept import SqlConcept
from app.models.tutor_chat_conversation import TutorChatConversation
from app.models.tutor_chat_message import TutorChatMessage
from app.models.user import User, UserRole
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


def class_groups(db: Session) -> list[str]:
    """Distinct non-empty class groups carried by users, for the filter dropdown.

    SQL's own copy rather than importing er_analytics.list_class_groups — the two
    analytics stacks stay decoupled even though the query is identical."""
    rows = (
        db.query(User.class_group)
        .filter(User.class_group.isnot(None), User.class_group != "")
        .distinct()
        .order_by(User.class_group.asc())
        .all()
    )
    return [r[0] for r in rows]


def _practice_question_ids(db: Session) -> list[int]:
    """Live bank SQL questions. Assessment-owned clones (owner_assessment_id set)
    are excluded, matching the practice scope of the per-question SQL analytics."""
    rows = (
        db.query(Question.id)
        .filter(Question.is_deleted == 0, Question.owner_assessment_id.is_(None))
        .all()
    )
    return [r[0] for r in rows]


def class_overview(db: Session, class_group: Optional[str] = None) -> dict:
    """Cohort-wide SQL analytics. Mirrors er_analytics.class_overview, but SQL has
    no rubric/checks — weakness is measured per *concept* instead of per dimension.

    For each concept, over every practice question tagged with it, we count the
    (student, question) pairs the student has attempted (has a UserProgress row)
    and the share not completed — the binary-correctness analog of ERD's fail rate.
    Students only; staff test attempts stay out of every number."""
    question_ids = _practice_question_ids(db)
    if not question_ids:
        return {"concepts": [], "questions": []}

    # One row per (student, attempted question): completion + attempt count.
    progress_q = (
        db.query(
            UserProgress.user_id,
            UserProgress.question_id,
            UserProgress.completed,
            UserProgress.attempts_count,
        )
        .join(User, User.id == UserProgress.user_id)
        .filter(
            UserProgress.question_id.in_(question_ids),
            User.role == UserRole.STUDENT,
        )
    )
    if class_group is not None:
        progress_q = progress_q.filter(User.class_group == class_group)

    # UserProgress is unique per (user, question), so each row is a distinct pair.
    by_question: dict[int, list] = defaultdict(list)
    for uid, qid, completed, attempts in progress_q.all():
        by_question[qid].append((uid, bool(completed), attempts or 0))

    # concept -> tagged practice question ids
    concept_questions: dict[int, set] = defaultdict(set)
    for cid, qid in (
        db.query(QuestionConcept.concept_id, QuestionConcept.question_id)
        .filter(QuestionConcept.question_id.in_(question_ids))
        .all()
    ):
        concept_questions[cid].add(qid)

    concept_meta = {
        c.id: c
        for c in db.query(SqlConcept).filter(SqlConcept.is_active == 1).all()
    }

    concepts = []
    for cid, qids in concept_questions.items():
        meta = concept_meta.get(cid)
        if meta is None:  # tag points at a removed/inactive concept — skip it
            continue
        total_pairs = not_completed = 0
        students: set[int] = set()
        questions: set[int] = set()
        for qid in qids:
            for uid, completed, _ in by_question.get(qid, []):
                total_pairs += 1
                students.add(uid)
                questions.add(qid)
                if not completed:
                    not_completed += 1
        if total_pairs == 0:  # nothing attempted for this concept yet
            continue
        concepts.append({
            "concept_id": cid,
            "slug": meta.slug,
            "display_name": meta.display_name,
            "category": meta.category,
            "not_completed_rate": not_completed / total_pairs,
            "students": len(students),
            "questions": len(questions),
            "pairs": total_pairs,
        })
    concepts.sort(key=lambda c: c["not_completed_rate"], reverse=True)

    q_meta = dict(
        db.query(Question.id, Question.title)
        .filter(Question.id.in_(by_question.keys())).all()
    ) if by_question else {}
    questions = []
    for qid, rows in sorted(by_question.items()):
        students_n = len(rows)
        completed_n = sum(1 for _, c, _ in rows if c)
        questions.append({
            "question_id": qid,
            "title": q_meta.get(qid, ""),
            "attempts": sum(a for _, _, a in rows),
            "students": students_n,
            "completion_rate": completed_n / students_n if students_n else 0.0,
        })

    return {"concepts": concepts, "questions": questions}


def student_engagement(db: Session, class_group: Optional[str] = None) -> dict:
    """Per-student SQL usage across every practice question, for the admin SQL tab.

    Students only. Mirrors er_analytics.student_engagement; SQL correctness is
    binary, so 'completion %' (questions completed / questions tried) stands in
    for ERD's best-score percent."""
    student_q = db.query(User.id).filter(User.role == UserRole.STUDENT)
    if class_group is not None:
        student_q = student_q.filter(User.class_group == class_group)
    student_ids = {row[0] for row in student_q.all()}

    per: dict[int, dict] = {}

    def slot(uid: int) -> dict:
        return per.setdefault(uid, {
            "user_id": uid,
            "practice_submissions": 0,
            "distinct_questions_tried": 0,
            "questions_completed": 0,
            "completion_percent": None,
            "chatbot_queries": 0,
            "_first": None,
        })

    if student_ids:
        # Submissions + first activity from the full attempt history.
        for uid, count, first_at in (
            db.query(Attempt.user_id, func.count(Attempt.id),
                     func.min(Attempt.submitted_at))
            .join(Question, Question.id == Attempt.question_id)
            .filter(Question.is_deleted == 0,
                    Question.owner_assessment_id.is_(None),
                    Attempt.user_id.in_(student_ids))
            .group_by(Attempt.user_id).all()
        ):
            s = slot(uid)
            s["practice_submissions"] = int(count)
            s["_first"] = first_at

        # Questions tried / completed from progress (unique per (user, question)).
        for uid, tried, completed in (
            db.query(UserProgress.user_id,
                     func.count(UserProgress.question_id),
                     func.sum(UserProgress.completed))
            .join(Question, Question.id == UserProgress.question_id)
            .filter(Question.is_deleted == 0,
                    Question.owner_assessment_id.is_(None),
                    UserProgress.user_id.in_(student_ids))
            .group_by(UserProgress.user_id).all()
        ):
            s = slot(uid)
            tried = int(tried or 0)
            completed = int(completed or 0)
            s["distinct_questions_tried"] = tried
            s["questions_completed"] = completed
            s["completion_percent"] = round(completed / tried * 100) if tried else None

        # Tutor questions asked (user-role messages in question conversations).
        for uid, count in (
            db.query(TutorChatConversation.user_id, func.count(TutorChatMessage.id))
            .join(TutorChatMessage,
                  TutorChatMessage.conversation_id == TutorChatConversation.id)
            .filter(TutorChatConversation.context_type == "question",
                    TutorChatMessage.role == "user",
                    TutorChatConversation.user_id.in_(student_ids))
            .group_by(TutorChatConversation.user_id).all()
        ):
            slot(uid)["chatbot_queries"] = int(count)

    user_meta = {
        uid: {"email": email, "name": name, "class_group": group}
        for uid, email, name, group in (
            db.query(User.id, User.email, User.name, User.class_group)
            .filter(User.id.in_(per.keys())).all()
        )
    } if per else {}
    students = [
        {
            **{k: v for k, v in s.items() if not k.startswith("_")},
            "first_activity_at": s["_first"].isoformat() if s["_first"] else None,
            "email": user_meta.get(uid, {}).get("email", ""),
            "name": user_meta.get(uid, {}).get("name"),
            "class_group": user_meta.get(uid, {}).get("class_group"),
        }
        # Deterministic payload; the tab re-sorts client-side.
        for uid, s in sorted(per.items())
    ]

    completions = [s["completion_percent"] for s in per.values()
                   if s["completion_percent"] is not None]
    return {
        "totals": {
            "practice_submissions": sum(s["practice_submissions"] for s in per.values()),
            "students_engaged": sum(1 for s in per.values()
                                    if s["distinct_questions_tried"] > 0),
            "registered_students": len(student_ids),
            "avg_completion_percent": round(sum(completions) / len(completions))
                                      if completions else None,
            "chatbot_queries": sum(s["chatbot_queries"] for s in per.values()),
        },
        "students": students,
    }
