"""Regression test: the difficulty enum must persist lowercase VALUES, not NAMES.

All three enum-backed question models (questions, sql_lab_questions,
graph_questions) share a Postgres `difficulty` enum type whose labels are the
lowercase values 'easy'/'medium'/'hard'. SQLAlchemy's default for a Python enum
is to persist the member *name* ('EASY'/'MEDIUM'/'HARD'), which Postgres rejects
with:

    invalid input value for enum difficulty: "MEDIUM"

SQLite does not enforce enum labels, so this only surfaces on Postgres/Supabase.
These tests assert the column persists the lowercase values regardless of backend.
"""
from sqlalchemy.dialects import postgresql

from app.models.question import Question, Difficulty
from app.models.sql_lab_question import SqlLabQuestion
from app.models.graph_question import GraphQuestion

EXPECTED_LABELS = ["easy", "medium", "hard"]
ENUM_MODELS = (Question, SqlLabQuestion, GraphQuestion)


def test_enum_labels_are_lowercase_values():
    for model in ENUM_MODELS:
        enum_type = model.__table__.c.difficulty.type
        assert list(enum_type.enums) == EXPECTED_LABELS, (
            f"{model.__tablename__}.difficulty persists {list(enum_type.enums)}, "
            f"expected {EXPECTED_LABELS}"
        )


def test_member_binds_to_lowercase_value_on_postgres():
    enum_type = Question.__table__.c.difficulty.type
    bind = enum_type.bind_processor(postgresql.dialect())
    bound = bind(Difficulty.MEDIUM) if bind is not None else Difficulty.MEDIUM.value
    assert bound == "medium", f"bound value was {bound!r}, expected 'medium'"
