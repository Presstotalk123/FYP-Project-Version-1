"""One-off migration: create er_diagram_image_drafts on Postgres, and repair the
unique constraint if the table pre-dates it.

SQLite creates the table automatically at startup (main.py create_all), so this
is only needed against Postgres, once, before deploying image-draft autosave:
    python run_er_image_drafts_migration.py

Mirrors run_er_drafts_migration.py exactly; see its module docstring for the full
rationale. In short: `create_all(tables=[...])` only ever emits CREATE TABLE, so
against a pre-existing table it silently does nothing — and save_image_draft's
`ON CONFLICT (user_id, er_diagram_question_id)` upsert 500s without a real unique
constraint or index behind it. This checks for one and adds it if missing.

Safe to re-run: creating the table is idempotent via create_all, and the
constraint check only acts when the constraint is actually missing.
"""
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Engine

from app.database import Base, engine
from app.models.er_diagram_image_draft import ErDiagramImageDraft

CONSTRAINT_NAME = "uq_er_image_draft_user_question"
CONSTRAINT_COLUMNS = ("user_id", "er_diagram_question_id")


def _has_matching_unique(inspector, table_name: str) -> bool:
    """True if some unique constraint or unique index already covers exactly
    (user_id, er_diagram_question_id) — however it was declared. SQLAlchemy's
    inspector splits table-level UNIQUE constraints and explicit CREATE UNIQUE
    INDEX statements across get_unique_constraints() and get_indexes() (the
    split is dialect-dependent), so both are checked rather than assuming one.
    """
    target = set(CONSTRAINT_COLUMNS)
    for uc in inspector.get_unique_constraints(table_name):
        if set(uc["column_names"]) == target:
            return True
    for idx in inspector.get_indexes(table_name):
        if idx.get("unique") and set(idx["column_names"]) == target:
            return True
    return False


def ensure_schema(target_engine: Engine) -> str:
    """Create er_diagram_image_drafts if missing, and add the unique index
    save_image_draft's ON CONFLICT upsert depends on if a pre-existing table
    lacks one. Returns a human-readable status describing what actually
    happened — never a hardcoded "ready".
    """
    table_name = ErDiagramImageDraft.__table__.name
    existed_before = sa_inspect(target_engine).has_table(table_name)

    Base.metadata.create_all(bind=target_engine, tables=[ErDiagramImageDraft.__table__])

    if not existed_before:
        return "er_diagram_image_drafts created (table + unique constraint)"

    if _has_matching_unique(sa_inspect(target_engine), table_name):
        return "er_diagram_image_drafts ready (table and constraint already present)"

    # A pre-existing table without it: create_all leaves it strictly alone. Plain
    # DDL text rather than SQLAlchemy Index()/AddConstraint() objects — SQLite has
    # no ALTER TABLE ADD CONSTRAINT, and building an Index() here would register it
    # onto the live shared model metadata. A plain unique index satisfies
    # on_conflict_do_update(index_elements=...) identically on SQLite and Postgres.
    cols = ", ".join(CONSTRAINT_COLUMNS)
    with target_engine.begin() as conn:
        conn.execute(text(f"CREATE UNIQUE INDEX {CONSTRAINT_NAME} ON {table_name} ({cols})"))
    return f"er_diagram_image_drafts repaired: added missing unique index {CONSTRAINT_NAME!r}"


def main() -> None:
    print(ensure_schema(engine))


if __name__ == "__main__":
    main()
