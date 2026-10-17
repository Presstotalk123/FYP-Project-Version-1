"""The relational-algebra engine: parse and evaluate RA with the course's semantics.

Pure Python, with no FastAPI or application-database imports, so it can be tested and
timed on its own. RA is evaluated directly, never translated to SQL.

    from app.core.ra import Database, parse, evaluate
    db = Database.from_sql(schema_sql, data_sql)
    result = evaluate(parse(answer_text, names=db.names()), db)
    result.columns, result.rows        # the answer
    result.statements                  # each statement's step-by-step tree, for the UI

Errors are raised as ``RAError`` with a code from ``errors.py`` and, where possible,
the line/column to underline in the editor.
"""
from app.core.ra.errors import RAError
from app.core.ra.evaluator import EvalOptions, EvalResult, evaluate
from app.core.ra.parser import parse
from app.core.ra.schema import Database, Table

__all__ = ["parse", "evaluate", "Database", "Table", "EvalOptions", "EvalResult", "RAError"]
