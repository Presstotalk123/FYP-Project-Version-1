"""Student leaderboards: per-lab ranking and an overall practice-completion ranking.

Both builders return *unmasked* payloads (full names, emails, student ids) so they
can be cached once and shared by every viewer; ``apply_viewer`` then strips or masks
identity for student viewers. Masking happens here on the server so other students'
real names and emails never reach a student's browser.

Completion semantics deliberately mirror the existing code so the leaderboard never
disagrees with other screens:
  - a lab task is solved once the student has any correct submission for it, and a
    lab is complete when every non-deleted task is solved (``lab_analytics`` /
    ``student_report.labs_completed_by_type``);
  - SQL/ER counts follow ``student_report.sql_questions_completed`` /
    ``erd_questions_completed``, batched across all students.
"""
import copy
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.er_diagram_question import ERDiagramQuestion
from app.models.erd_tutor_conversation import ErdTutorConversation
from app.models.lab import Lab
from app.models.lab_task import LabTask
from app.models.lab_task_submission import LabTaskSubmission
from app.models.progress import UserProgress
from app.models.question import Question
from app.models.user import User, UserRole

logger = logging.getLogger(__name__)

TASK_SOLVED = "solved"
TASK_ATTEMPTED = "attempted"
TASK_NOT_ATTEMPTED = "not_attempted"


def mask_name(name: Optional[str]) -> str:
    """Keep the first two letters of each word and star the rest.

    ``"Adolphus Chua"`` -> ``"Ad****** Ch**"``. A missing name becomes ``"Student"``.
    """
    if not name or not name.strip():
        return "Student"
    return " ".join(w[:2] + "*" * max(len(w) - 2, 0) for w in name.split())


def _display_name(name: Optional[str], email: str) -> str:
    return name.strip() if name and name.strip() else email


def _class_groups(db: Session) -> list[str]:
    """Distinct class groups of active students, for the filter dropdown."""
    rows = (
        db.query(User.class_group)
        .filter(
            User.role == UserRole.STUDENT,
            User.is_active == 1,
            User.class_group.isnot(None),
        )
        .distinct()
        .all()
    )
    return sorted(g for (g,) in rows if g)


def _assign_ranks(rows: list[dict], key) -> None:
    """Competition ranking (1, 1, 3) over rows already sorted by ``key``."""
    prev = None
    for idx, row in enumerate(rows):
        k = key(row)
        if k != prev:
            row["rank"] = idx + 1
            prev = k
        else:
            row["rank"] = rows[idx - 1]["rank"]


def lab_leaderboard(db: Session, lab_id: int, class_group: Optional[str] = None) -> Optional[dict]:
    """Rank the students who have submitted to one practice lab.

    Ordered by tasks solved (desc), ties broken by ``finished_at`` (asc): the time the
    student reached their current score, i.e. the latest of their first-correct
    submissions. Students with no submission to the lab are not listed. Returns
    ``None`` if the lab doesn't exist or is an assessment-owned clone.
    """
    lab = (
        db.query(Lab)
        .filter(Lab.id == lab_id, Lab.is_deleted == 0, Lab.owner_assessment_id.is_(None))
        .first()
    )
    if lab is None:
        return None

    tasks = (
        db.query(LabTask)
        .filter(LabTask.lab_id == lab_id, LabTask.is_deleted == 0)
        .order_by(LabTask.order_index.asc())
        .all()
    )
    task_ids = [t.id for t in tasks]
    task_id_set = set(task_ids)

    sub_q = (
        db.query(
            LabTaskSubmission.user_id,
            LabTaskSubmission.task_id,
            LabTaskSubmission.is_correct,
            LabTaskSubmission.submitted_at,
        )
        .join(User, User.id == LabTaskSubmission.user_id)
        .filter(
            LabTaskSubmission.lab_id == lab_id,
            User.role == UserRole.STUDENT,
            User.is_active == 1,
        )
    )
    if class_group is not None:
        sub_q = sub_q.filter(User.class_group == class_group)
    submissions = sub_q.order_by(
        LabTaskSubmission.submitted_at.asc(), LabTaskSubmission.id.asc()
    ).all()

    # Per student: submission count, tasks touched, and first-correct time per task.
    sub_count: dict[int, int] = defaultdict(int)
    attempted: dict[int, set] = defaultdict(set)
    first_correct: dict[int, dict[int, datetime]] = defaultdict(dict)
    for user_id, task_id, is_correct, submitted_at in submissions:
        if task_id not in task_id_set:
            continue  # submission to a since-deleted task
        sub_count[user_id] += 1
        attempted[user_id].add(task_id)
        if is_correct == 1 and task_id not in first_correct[user_id]:
            first_correct[user_id][task_id] = submitted_at

    user_ids = list(sub_count.keys())
    user_meta = {
        uid: (name, email, group)
        for uid, name, email, group in (
            db.query(User.id, User.name, User.email, User.class_group)
            .filter(User.id.in_(user_ids))
            .all()
        )
    } if user_ids else {}

    rows = []
    for uid in user_ids:
        name, email, group = user_meta[uid]
        solved = first_correct.get(uid, {})
        finished_at = max(solved.values()) if solved else None
        rows.append({
            "rank": 0,
            "student_id": uid,
            "display_name": _display_name(name, email),
            "name": name,
            "email": email,
            "class_group": group,
            "tasks_correct": len(solved),
            "total_tasks": len(tasks),
            "task_status": [
                TASK_SOLVED if tid in solved
                else TASK_ATTEMPTED if tid in attempted[uid]
                else TASK_NOT_ATTEMPTED
                for tid in task_ids
            ],
            "submissions": sub_count[uid],
            "finished_at": finished_at,
            "completed": len(tasks) > 0 and len(solved) == len(tasks),
            "is_me": False,
        })

    # Students with nothing solved have no finished_at; they sort after everyone
    # with the same (zero) score that does — i.e. among themselves, by name.
    rows.sort(key=lambda r: (
        -r["tasks_correct"],
        r["finished_at"] is None,
        r["finished_at"] or datetime.min,
        r["display_name"].lower(),
    ))
    _assign_ranks(rows, key=lambda r: (r["tasks_correct"], r["finished_at"]))

    return {
        "lab_id": lab.id,
        "title": lab.title,
        "lab_type": lab.lab_type,
        "tasks": [
            {"task_id": t.id, "title": t.title, "order_index": t.order_index}
            for t in tasks
        ],
        "rows": rows,
        "class_groups": _class_groups(db),
        "my_rank": None,
        "correctness_hidden": False,
    }


def _sql_completed_by_user(db: Session) -> dict[int, int]:
    """Batched ``student_report.sql_questions_completed`` for every user."""
    rows = (
        db.query(UserProgress.user_id, func.count(UserProgress.id))
        .join(Question, UserProgress.question_id == Question.id)
        .filter(
            UserProgress.completed == 1,
            Question.is_deleted == 0,
            Question.owner_assessment_id.is_(None),
        )
        .group_by(UserProgress.user_id)
        .all()
    )
    return {uid: n for uid, n in rows}


def _erd_completed_by_user(db: Session) -> dict[int, int]:
    """Batched ``student_report.erd_questions_completed`` for every user."""
    rows = (
        db.query(ErdTutorConversation.user_id, ErdTutorConversation.last_submit_score)
        .join(
            ERDiagramQuestion,
            ERDiagramQuestion.id == ErdTutorConversation.er_diagram_question_id,
        )
        .filter(
            ErdTutorConversation.context_type == "standalone",
            ErdTutorConversation.er_diagram_question_id.isnot(None),
            ErdTutorConversation.last_submit_score.isnot(None),
            ERDiagramQuestion.is_deleted == 0,
            ERDiagramQuestion.owner_assessment_id.is_(None),
        )
        .all()
    )
    completed: dict[int, int] = defaultdict(int)
    for user_id, raw_score in rows:
        try:
            data = json.loads(raw_score)
            if isinstance(data, dict) and data.get("label") == "pass":
                completed[user_id] += 1
        except (TypeError, ValueError):
            logger.warning("Unreadable last_submit_score for user %s", user_id)
    return completed


def _labs_completed_by_user(db: Session) -> dict[int, int]:
    """Batched ``student_report.labs_completed_by_type`` (SQL + graph summed)."""
    lab_task_counts = dict(
        db.query(LabTask.lab_id, func.count(LabTask.id))
        .join(Lab, Lab.id == LabTask.lab_id)
        .filter(
            Lab.is_published == 1,
            Lab.is_deleted == 0,
            Lab.owner_assessment_id.is_(None),
            LabTask.is_deleted == 0,
        )
        .group_by(LabTask.lab_id)
        .all()
    )
    if not lab_task_counts:
        return {}

    solved = (
        db.query(
            LabTaskSubmission.user_id,
            LabTaskSubmission.lab_id,
            func.count(func.distinct(LabTaskSubmission.task_id)),
        )
        .join(LabTask, LabTask.id == LabTaskSubmission.task_id)
        .filter(
            LabTaskSubmission.lab_id.in_(lab_task_counts.keys()),
            LabTaskSubmission.is_correct == 1,
            LabTask.is_deleted == 0,
        )
        .group_by(LabTaskSubmission.user_id, LabTaskSubmission.lab_id)
        .all()
    )
    completed: dict[int, int] = defaultdict(int)
    for user_id, lab_id, n_correct in solved:
        if n_correct >= lab_task_counts[lab_id]:
            completed[user_id] += 1
    return completed


def overall_leaderboard(db: Session, class_group: Optional[str] = None) -> dict:
    """Rank every active student by SQL + ER + labs completed (ties share a rank)."""
    student_q = db.query(User.id, User.name, User.email, User.class_group).filter(
        User.role == UserRole.STUDENT,
        User.is_active == 1,
    )
    if class_group is not None:
        student_q = student_q.filter(User.class_group == class_group)
    students = student_q.all()

    sql = _sql_completed_by_user(db)
    erd = _erd_completed_by_user(db)
    labs = _labs_completed_by_user(db)

    rows = []
    for uid, name, email, group in students:
        s, e, l = sql.get(uid, 0), erd.get(uid, 0), labs.get(uid, 0)
        rows.append({
            "rank": 0,
            "student_id": uid,
            "display_name": _display_name(name, email),
            "name": name,
            "email": email,
            "class_group": group,
            "sql_completed": s,
            "erd_completed": e,
            "labs_completed": l,
            "total": s + e + l,
            "is_me": False,
        })

    rows.sort(key=lambda r: (-r["total"], r["display_name"].lower()))
    _assign_ranks(rows, key=lambda r: r["total"])

    return {"rows": rows, "class_groups": _class_groups(db), "my_rank": None}


def apply_viewer(payload: dict, viewer: User) -> dict:
    """Tailor a cached, unmasked payload to the viewer.

    Staff/admin get it unchanged (the raw ``name`` key is dropped by the response
    model). Students get other students' names masked, every ``student_id``/``email``
    and raw ``name`` removed, their own row flagged ``is_me`` (unmasked), and
    ``my_rank`` set. Works on a deep copy so the cached payload is never mutated.
    """
    if viewer.role != UserRole.STUDENT:
        return payload

    out = copy.deepcopy(payload)
    for row in out["rows"]:
        if row["student_id"] == viewer.id:
            row["is_me"] = True
            out["my_rank"] = row["rank"]
        else:
            row["display_name"] = mask_name(row["name"])
        row["student_id"] = None
        row["email"] = None
        row.pop("name", None)
    return out
