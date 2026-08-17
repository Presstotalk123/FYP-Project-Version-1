"""One-off migration: create er_diagram_drafts on Postgres, and repair the
unique constraint if the table pre-dates it.

SQLite creates the table automatically at startup (main.py create_all), so this
is only needed against Postgres, once, before deploying draft autosave:
    python run_er_drafts_migration.py

Why the constraint check matters: `create_all(tables=[...])` only ever emits
CREATE TABLE — against a table that already exists (e.g. left over from an
earlier iteration of this branch, or a Postgres deploy from a different
commit, or even a local SQLite db from a partial dev run) it does nothing at
all, silently. `save_draft`'s upsert relies on
`ON CONFLICT (user_id, er_diagram_question_id)` matching a real unique
constraint or index; without one, every autosave raises
`InvalidColumnReference: there is no unique or exclusion constraint matching
the ON CONFLICT specification` — i.e. every autosave 500s in production while
this script printed "ready" and told nobody. Mirrors
run_er_submissions_migration.py, which handles the equivalent gap for its
indexes.

Safe to re-run: creating the table is idempotent via create_all, and the
constraint check only acts when the constraint is actually missing.
"""
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Engine

from app.database import Base, engine
from app.models.er_diagram_draft import ErDiagramDraft

CONSTRAINT_NAME = "uq_er_draft_user_question"
CONSTRAINT_COLUMNS = ("user_id", "er_diagram_question_id")


def _has_matching_unique(inspector, table_name: str) -> bool:
    """True if some unique constraint or unique index already covers exactly
    (user_id, er_diagram_question_id) — however it was declared. SQLAlchemy's
    inspector splits table-level UNIQUE constraints and explicit CREATE UNIQUE
    INDEX statements across get_unique_constraints() and get_indexes() (the
    split is dialect-dependent — see the note in
    tests/er_drafts/test_er_drafts_service.py), so both are checked rather
    than assuming one.
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
    """Create er_diagram_drafts if missing, and add the unique index
    save_draft's ON CONFLICT upsert depends on if a pre-existing table lacks
    one. Returns a human-readable status describing what actually happened —
    never a hardcoded "ready" — since "nothing needed doing", "table just
    created" and "constraint repaired" are different outcomes worth telling
    apart in a deploy log.
    """
    table_name = ErDiagramDraft.__table__.name
    existed_before = sa_inspect(target_engine).has_table(table_name)

    Base.metadata.create_all(bind=target_engine, tables=[ErDiagramDraft.__table__])

    if not existed_before:
        return "er_diagram_drafts created (table + unique constraint)"

    if _has_matching_unique(sa_inspect(target_engine), table_name):
        return "er_diagram_drafts ready (table and constraint already present)"

    # A pre-existing table without it: create_all leaves it strictly alone (it
    # only ever emits CREATE TABLE, never ALTERs an existing one). Plain DDL
    # text rather than SQLAlchemy's Index()/AddConstraint() objects: SQLite
    # has no ALTER TABLE ADD CONSTRAINT syntax at all, and building an Index()
    # object here would register it onto ErDiagramDraft.__table__ — the live,
    # shared model metadata used everywhere else in the app — for the rest of
    # the process, which would then get created a second time (with a
    # colliding name) the next time this table is built fresh via create_all
    # elsewhere in the same run. A plain unique index satisfies
    # `on_conflict_do_update(index_elements=...)` identically to a named
    # constraint on both SQLite and Postgres (Postgres's ON CONFLICT performs
    # inference over any matching unique index, not specifically a named
    # constraint), and mirrors how run_er_submissions_migration.py repairs its
    # own missing indexes.
    cols = ", ".join(CONSTRAINT_COLUMNS)
    with target_engine.begin() as conn:
        conn.execute(text(f"CREATE UNIQUE INDEX {CONSTRAINT_NAME} ON {table_name} ({cols})"))
    return f"er_diagram_drafts repaired: added missing unique index {CONSTRAINT_NAME!r}"


def main() -> None:
    print(ensure_schema(engine))


if __name__ == "__main__":
    main()
