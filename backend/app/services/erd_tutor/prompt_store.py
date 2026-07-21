"""Registry + resolver for admin-editable LangGraph prompts.

Code constants in ``prompts.py`` are the canonical defaults; a row in
``erd_prompt_versions`` with ``is_active=1`` overrides one. ``get_prompt``
must NEVER raise for a registered key: any DB problem (missing table,
connection error) falls back to the code default — prompt editing can not
be allowed to break grading or tutoring.
"""

import logging

from sqlalchemy.exc import OperationalError

from app.services.erd_tutor import prompts

logger = logging.getLogger(__name__)

PROMPT_REGISTRY = {
    "tutor_system": {
        "default": prompts.TUTOR_SYSTEM,
        "label": "Query Tutor behavior",
        "description": "System prompt for the AI tutor when students ask questions (IBL style, hint levels, refusal policy).",
    },
    "grade_system": {
        "default": prompts.GRADE_SYSTEM,
        "label": "Grading policy",
        "description": "System prompt for the strict submission grader (status policy, naming tolerance, partial-credit rules).",
    },
}


def get_prompt(key: str) -> str:
    default = PROMPT_REGISTRY[key]["default"]  # KeyError for unregistered keys is intentional
    try:
        # Imported lazily so a broken DB layer can never break module import,
        # and so tests can monkeypatch app.database.SessionLocal.
        import app.database as app_db
        from app.models.erd_prompt_version import ErdPromptVersion

        db = app_db.SessionLocal()
        try:
            # The writer enforces "at most one active per key" transactionally;
            # order by newest version so behavior stays deterministic even if
            # that invariant is ever violated. (A partial unique index is not
            # used on purpose: SQLite ignores postgresql_where — see the
            # broken-partial-index note in main.py.)
            rows = (db.query(ErdPromptVersion)
                      .filter(ErdPromptVersion.prompt_key == key,
                              ErdPromptVersion.is_active == 1)
                      .order_by(ErdPromptVersion.version_no.desc())
                      .limit(2)
                      .all())
            if len(rows) == 2:
                logger.error(
                    "prompt_store: invariant violated — multiple active rows for %r; "
                    "serving newest (v%s)", key, rows[0].version_no
                )
            return rows[0].content if rows else default
        finally:
            db.close()
    except OperationalError:
        logger.error(
            "prompt_store: database locked/unavailable while resolving %r — "
            "serving code default", key
        )
        return default
    except Exception:
        logger.exception("prompt_store: falling back to code default for %r", key)
        return default
