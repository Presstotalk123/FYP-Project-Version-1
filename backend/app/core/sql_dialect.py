"""
Runtime, best-effort MySQL -> SQLite query conversion for *student* queries.

Students often write SQL in the MySQL dialect they learned elsewhere (LeetCode, prior
courses): DATEDIFF, CURDATE, DATE_ADD, backtick-quoted identifiers, etc. This platform runs
SQLite server-side, which lacks those, so such a query fails with e.g. `no such function:
DATEDIFF` even when the logic is correct. `to_sqlite` transpiles the query to SQLite via
sqlglot so the executors can transparently re-run it after the original fails.

This is deliberately a *fallback*: callers run the student's query as-is first and only reach
for `to_sqlite` when it fails, so a rewrite is never applied to an already-working query.

Not to be confused with the frontend authoring-time converter
(`frontend/src/utils/sqlDialect.ts`), which is a conservative *regex* transform for DDL/type
names in setup scripts and does not touch functions. This module is runtime, expression-aware,
and AST-based (sqlglot).
"""
import logging
import re
from typing import Optional

import sqlglot
from sqlglot import exp
from sqlglot.dialects.sqlite import SQLite

# sqlglot emits a warning when it can't fully map a construct (e.g. an unsupported DATEDIFF
# unit). We already treat any imperfect/failed transpile as "fall back to the original", so
# these warnings are noise — quiet them.
logging.getLogger("sqlglot").setLevel(logging.ERROR)

_WHITESPACE = re.compile(r"\s+")


# ─────────────────────────── supplementary SQLite dialect ───────────────────────────
# sqlglot's stock SQLite generator leaves several common MySQL functions unmapped — it emits
# e.g. `YEAR(DATE(d))` or `LEFT(s, 3)` verbatim, which SQLite has no function for, so the
# rewrite still fails. `_SQLiteExtended` overrides how those specific expression nodes render
# so they become valid SQLite. Each override was verified to run and return the expected value
# on SQLite; a few carry minor semantic caveats (noted inline). Anything not listed here keeps
# sqlglot's default SQLite behavior.


def _strftime_part(fmt: str):
    """Render a date-part extractor (YEAR/MONTH/…) as an integer strftime() on SQLite."""
    return lambda self, e: f"CAST(STRFTIME('{fmt}', {self.sql(e, 'this')}) AS INTEGER)"


def _left_sql(self, e: exp.Expression) -> str:
    # LEFT(s, n) -> first n characters
    return f"SUBSTR({self.sql(e, 'this')}, 1, {self.sql(e, 'expression')})"


def _right_sql(self, e: exp.Expression) -> str:
    # RIGHT(s, n) -> last n characters (SQLite reads a negative start as "from the end")
    return f"SUBSTR({self.sql(e, 'this')}, -({self.sql(e, 'expression')}))"


def _day_of_week_sql(self, e: exp.Expression) -> str:
    # MySQL DAYOFWEEK: 1=Sunday..7=Saturday. SQLite strftime('%w'): 0=Sunday..6=Saturday.
    return f"(CAST(STRFTIME('%w', {self.sql(e, 'this')}) AS INTEGER) + 1)"


def _date_sub_sql(self, e: exp.Expression) -> str:
    # DATE_SUB(d, INTERVAL n UNIT) -> DATE(d, '-n UNIT'). (sqlglot maps DATE_ADD but not
    # DATE_SUB for SQLite.) Built via string concat so a non-literal amount still works.
    unit = e.unit.name if e.unit else "DAY"
    return f"DATE({self.sql(e, 'this')}, '-' || {self.sql(e, 'expression')} || ' {unit}')"


def _anonymous_sql(self, e: exp.Anonymous) -> str:
    # NOW() has no typed node (parses as Anonymous); map it, pass everything else through
    # unchanged. NOTE: SQLite DATETIME('now') is UTC, whereas MySQL NOW() is server-local.
    if e.name.upper() == "NOW":
        return "DATETIME('now')"
    return self.anonymous_sql(e)


class _SQLiteExtended(SQLite):
    class Generator(SQLite.Generator):
        TRANSFORMS = {
            **SQLite.Generator.TRANSFORMS,
            exp.Year: _strftime_part("%Y"),
            exp.Month: _strftime_part("%m"),
            exp.Day: _strftime_part("%d"),
            exp.Hour: _strftime_part("%H"),
            exp.Minute: _strftime_part("%M"),
            exp.Second: _strftime_part("%S"),
            # NOTE: exp.Week is deliberately NOT mapped. MySQL WEEK() has 8 week-numbering
            # modes (Sunday- vs Monday-based, differing week-1 rules); no single SQLite
            # strftime translation reproduces them, so a silent conversion could grade a
            # correct query wrong (grading is by result hash). Better to let WEEK() fail
            # loudly with `no such function: WEEK` than to mis-grade invisibly.
            exp.DayOfWeek: _day_of_week_sql,
            exp.Left: _left_sql,
            exp.Right: _right_sql,
            exp.DateSub: _date_sub_sql,
            exp.Anonymous: _anonymous_sql,
        }


def _normalized(sql: str) -> str:
    """
    Whitespace- and case-insensitive key used only to decide whether a transpile changed
    anything meaningful. Stripping all whitespace and uppercasing means cosmetic reformatting
    (lowercase keywords, indentation, `a,b` vs `a, b`) compares equal, while a genuine token
    rewrite (DATEDIFF -> CAST(JULIANDAY...), backticks -> double quotes) compares different.
    """
    return _WHITESPACE.sub("", sql).upper()


def to_sqlite(query: str) -> Optional[str]:
    """
    Return a SQLite-dialect rewrite of `query` when it contains MySQL-specific syntax that
    SQLite lacks, or None when there is nothing to convert / the query can't be parsed.

    Intended to be called only after `query` has already failed against SQLite, so the rewrite
    is a rescue attempt and never alters a working query. Returning None means "keep the
    student's original error".

    Examples that convert (return a rewritten string):
        SELECT DATEDIFF('2020-01-10','2020-01-01')  -> SELECT CAST((JULIANDAY(...) - ...) AS INTEGER)
        SELECT YEAR(d)                              -> SELECT CAST(STRFTIME('%Y', DATE(d)) AS INTEGER)
        SELECT LEFT(s, 3)                           -> SELECT SUBSTR(s, 1, 3)
        SELECT NOW()                                -> SELECT DATETIME('now')
        SELECT `id` FROM `users`                    -> SELECT "id" FROM "users"
    (Date-part / string coverage beyond sqlglot's stock SQLite dialect comes from
    `_SQLiteExtended` above.)

    Examples that return None (no dialect rewrite worth re-running):
        SELECT foo FROM t          (valid shape, bad column — a real error, not a dialect issue)
        select name from studets   (lowercase typo — only cosmetic reformatting)
        not sql at all             (unparseable — sqlglot raises, we fall back)

    Note: a mangled-but-parseable string (e.g. `SELCT * FORM t`, which sqlglot leniently reads
    as aliases) may return a rewrite that merely fails again on re-run — harmless, since the
    caller then surfaces the student's original error either way.
    """
    if not query or not query.strip():
        return None

    try:
        statements = sqlglot.transpile(query, read="mysql", write=_SQLiteExtended)
    except Exception:
        # Not parseable as MySQL — genuine typo/garbage, nothing to rewrite.
        return None

    if not statements:
        return None

    converted = ";\n".join(statements)

    # Only worth re-running when the rewrite changed something beyond whitespace/case. If it
    # didn't, the original failure wasn't a dialect problem, so don't waste a second execution.
    if _normalized(converted) == _normalized(query):
        return None

    return converted
