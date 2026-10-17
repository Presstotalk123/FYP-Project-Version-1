"""Prepared RA questions, kept in memory so the test databases are built once, not per answer.

Building a question's test suite takes from a few ms up to a few seconds (core/ra/suite.py);
grading one answer against it takes a few ms. The cache is per process and keyed by the
question's text, so an edited schema or model answer is simply a new entry.
"""
import threading
from collections import OrderedDict
from typing import Callable, Optional, Tuple

from app.core.ra import EvalOptions
from app.core.ra.grader import PreparedQuestion
from app.core.ra.schema import Database

_CACHE_SIZE = 64
_cache: "OrderedDict[tuple, PreparedQuestion]" = OrderedDict()
_lock = threading.Lock()


def cached(key: tuple, build: Callable[[], PreparedQuestion]) -> PreparedQuestion:
    """The prepared question for ``key``, built with ``build()`` on a miss."""
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    question = build()
    with _lock:
        _cache[key] = question
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return question


def prepared(schema_sql: str, model_answer: str, data_sql: str = "", *,
             options: EvalOptions = EvalOptions()) -> PreparedQuestion:
    """The prepared question for this text (the playground). Raises RAError for a bad
    schema or model answer."""
    return cached(("text", schema_sql, data_sql or "", model_answer, options),
                  lambda: PreparedQuestion(schema_sql, model_answer, data_sql, options=options))


def structure_database(question: PreparedQuestion) -> Tuple[Database, str]:
    """Where to show the student's steps: the question's data, or else a generated test
    database with plenty of tuples (the first ones are small random ones, see suite.py)."""
    if question.sample is not None:
        return question.sample, "sample"
    candidates = question.suite.databases[1:61] or question.suite.databases
    best: Optional[Database] = max(candidates, key=lambda d: sum(len(t.rows) for t in d.tables))
    return best, "generated"
