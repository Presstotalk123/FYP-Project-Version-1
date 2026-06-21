from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.question import Question, Difficulty
from app.models.er_diagram_question import ERDiagramQuestion
from app.models.sql_lab_question import SqlLabQuestion
from app.models.graph_question import GraphQuestion
from app.schemas.problem import ProblemCounts, ProblemListItem, ProblemListResponse

router = APIRouter(prefix="/problems", tags=["problems"])


def _role_value(role) -> str:
    # Surface admin authors as "staff" so the problem-list tag matches the author
    # filter, which groups admin with staff (User.role.in_([STAFF, ADMIN])).
    value = role.value if isinstance(role, UserRole) else str(role).strip().lower()
    return "staff" if value == "admin" else value


@router.get("", response_model=ProblemListResponse)
def list_problems(
    type: Optional[Literal["sql", "erd", "sqllab", "graph"]] = Query(None),
    difficulty: Optional[Literal["easy", "medium", "hard"]] = Query(None),
    search: Optional[str] = Query(None),
    author: Optional[Literal["all", "staff", "students"]] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    author_norm = author or "all"
    items: list[ProblemListItem] = []

    include_sql = type in (None, "sql")
    include_erd = type in (None, "erd")
    include_sqllab = type in (None, "sqllab")
    include_graph = type in (None, "graph")

    if include_sql:
        sql_query = (
            db.query(Question, User.role)
            .join(User, Question.created_by == User.id)
            .filter(Question.is_deleted == 0)
        )
        if difficulty:
            sql_query = sql_query.filter(Question.difficulty == Difficulty(difficulty))
        if search:
            term = f"%{search}%"
            sql_query = sql_query.filter(
                (Question.title.ilike(term)) | (Question.description.ilike(term))
            )
        if author_norm == "staff":
            sql_query = sql_query.filter(User.role.in_([UserRole.STAFF, UserRole.ADMIN]))
        elif author_norm == "students":
            sql_query = sql_query.filter(User.role == UserRole.STUDENT)
        for question, role in sql_query.all():
            role_value = _role_value(role)
            items.append(
                ProblemListItem(
                    type="sql",
                    id=question.id,
                    title=question.title,
                    difficulty=question.difficulty.value,
                    created_by=question.created_by,
                    created_by_role=role_value,
                    created_at=question.created_at,
                )
            )

    if include_erd:
        erd_query = (
            db.query(ERDiagramQuestion, User.role)
            .join(User, ERDiagramQuestion.created_by == User.id)
            .filter(ERDiagramQuestion.is_deleted == 0)
        )
        if difficulty:
            erd_query = erd_query.filter(
                ERDiagramQuestion.difficulty_label == difficulty.capitalize()
            )
        if search:
            term = f"%{search}%"
            erd_query = erd_query.filter(
                (ERDiagramQuestion.title.ilike(term))
                | (ERDiagramQuestion.problem_statement.ilike(term))
            )
        if author_norm == "staff":
            erd_query = erd_query.filter(User.role.in_([UserRole.STAFF, UserRole.ADMIN]))
        elif author_norm == "students":
            erd_query = erd_query.filter(User.role == UserRole.STUDENT)
        for question, role in erd_query.all():
            role_value = _role_value(role)
            items.append(
                ProblemListItem(
                    type="erd",
                    id=question.id,
                    title=question.title,
                    difficulty=question.difficulty_label.lower(),
                    created_by=question.created_by,
                    created_by_role=role_value,
                    created_at=question.created_at,
                )
            )

    if include_sqllab:
        slq = (
            db.query(SqlLabQuestion, User.role)
            .join(User, SqlLabQuestion.created_by == User.id)
            .filter(SqlLabQuestion.is_deleted == 0)
        )
        if difficulty:
            slq = slq.filter(SqlLabQuestion.difficulty == Difficulty(difficulty))
        if search:
            term = f"%{search}%"
            slq = slq.filter(
                (SqlLabQuestion.title.ilike(term)) | (SqlLabQuestion.description.ilike(term))
            )
        if author_norm == "staff":
            slq = slq.filter(User.role.in_([UserRole.STAFF, UserRole.ADMIN]))
        elif author_norm == "students":
            slq = slq.filter(User.role == UserRole.STUDENT)
        for question, role in slq.all():
            role_value = _role_value(role)
            items.append(
                ProblemListItem(
                    type="sqllab",
                    id=question.id,
                    title=question.title,
                    difficulty=question.difficulty.value,
                    created_by=question.created_by,
                    created_by_role=role_value,
                    created_at=question.created_at,
                )
            )

    if include_graph:
        gq = (
            db.query(GraphQuestion, User.role)
            .join(User, GraphQuestion.created_by == User.id)
            .filter(GraphQuestion.is_deleted == 0)
        )
        if difficulty:
            gq = gq.filter(GraphQuestion.difficulty == Difficulty(difficulty))
        if search:
            term = f"%{search}%"
            gq = gq.filter(
                (GraphQuestion.title.ilike(term)) | (GraphQuestion.description.ilike(term))
            )
        if author_norm == "staff":
            gq = gq.filter(User.role.in_([UserRole.STAFF, UserRole.ADMIN]))
        elif author_norm == "students":
            gq = gq.filter(User.role == UserRole.STUDENT)
        for question, role in gq.all():
            role_value = _role_value(role)
            items.append(
                ProblemListItem(
                    type="graph",
                    id=question.id,
                    title=question.title,
                    difficulty=question.difficulty.value,
                    created_by=question.created_by,
                    created_by_role=role_value,
                    created_at=question.created_at,
                )
            )

    items.sort(key=lambda item: item.created_at, reverse=True)

    sql_count = db.query(Question).filter(Question.is_deleted == 0).count()
    erd_count = db.query(ERDiagramQuestion).filter(ERDiagramQuestion.is_deleted == 0).count()
    sqllab_count = db.query(SqlLabQuestion).filter(SqlLabQuestion.is_deleted == 0).count()
    graph_count = db.query(GraphQuestion).filter(GraphQuestion.is_deleted == 0).count()
    counts = ProblemCounts(
        all=sql_count + erd_count + sqllab_count + graph_count,
        sql=sql_count, erd=erd_count, sqllab=sqllab_count, graph=graph_count,
    )
    return ProblemListResponse(items=items, counts=counts)
