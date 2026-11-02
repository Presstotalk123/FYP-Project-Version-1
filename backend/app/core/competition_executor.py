"""Bounded, canonical SQLite execution for immutable incident fixtures.

Fixtures contain data only: reference queries never become database views. A
student can select a published item, never an arbitrary database filename.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time

import sqlglot
from sqlglot import exp

from app.config import settings
from app.core.query_deadline import attach_deadline


class CompetitionSQLError(ValueError):
    pass


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def parse_select(sql: str):
    if not sql.strip() or len(sql) > settings.COMPETITION_SQL_MAX_CHARS:
        raise CompetitionSQLError("Enter one SELECT query within the SQL size limit.")
    try:
        nodes = [n for n in sqlglot.parse(sql, read="sqlite") if n is not None]
    except (sqlglot.errors.SqlglotError, RecursionError) as exc:
        raise CompetitionSQLError("The query could not be parsed as SQLite SQL.") from exc
    if len(nodes) != 1 or not isinstance(nodes[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        raise CompetitionSQLError("Only one read-only SELECT query is allowed.")
    for node in nodes[0].walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Command)):
            raise CompetitionSQLError("Only read-only SELECT queries are allowed.")
    return nodes[0]


def _limits(conn):
    conn.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1_000_000)
    conn.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 250_000)
    conn.setlimit(sqlite3.SQLITE_LIMIT_COLUMN, 100)
    conn.setlimit(sqlite3.SQLITE_LIMIT_EXPR_DEPTH, 100)
    conn.setlimit(sqlite3.SQLITE_LIMIT_COMPOUND_SELECT, 20)
    conn.setlimit(sqlite3.SQLITE_LIMIT_ATTACHED, 0)
    conn.enable_load_extension(False)


def _authorizer(action, arg1, arg2, _database, _trigger):
    if action == sqlite3.SQLITE_FUNCTION:
        # Date/time functions using 'now' and randomness are deliberately excluded
        # from the reproducible repair contract, as are I/O/extension functions.
        if (arg2 or "").lower() in {"load_extension", "readfile", "writefile", "random", "randomblob"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action in {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_RECURSIVE}:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def fixture_path(schema: str, seed: str) -> Path:
    root = Path(settings.COMPETITION_DB_PATH).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{digest({'schema': schema, 'seed': seed, 'format': 1})}.db"
    if target.exists():
        return target
    try:
        ddl = [s for s in sqlglot.parse(schema, read="sqlite") if s is not None]
        inserts = [s for s in sqlglot.parse(seed, read="sqlite") if s is not None]
    except sqlglot.errors.SqlglotError as exc:
        raise CompetitionSQLError("Fixture schema or seed SQL could not be parsed.") from exc
    if not ddl or len(ddl) + len(inserts) > 500:
        raise CompetitionSQLError("Fixtures require a bounded schema and seed.")
    for node in ddl:
        if not isinstance(node, exp.Create) or str(node.args.get("kind", "")).upper() not in {"TABLE", "INDEX"}:
            raise CompetitionSQLError("Fixture schemas may only create tables and indexes.")
        if node.find(exp.Select) or node.find(exp.Command) or node.find(exp.Func):
            raise CompetitionSQLError("Fixture schemas cannot execute queries or commands.")
    for node in inserts:
        if not isinstance(node, exp.Insert) or not isinstance(node.expression, exp.Values):
            raise CompetitionSQLError("Fixture seeds may only INSERT literal VALUES.")
        if node.find(exp.Func) or node.find(exp.Select):
            raise CompetitionSQLError("Fixture seeds must be deterministic literal records.")
    fd, temporary = tempfile.mkstemp(prefix="fixture-", suffix=".db", dir=root)
    os.close(fd)
    conn = None
    try:
        conn = sqlite3.connect(temporary)
        _limits(conn)
        attach_deadline(conn, settings.COMPETITION_QUERY_SECONDS, grace_seconds=0)
        conn.execute("PRAGMA foreign_keys=ON")
        for node in ddl + inserts:
            conn.execute(node.sql(dialect="sqlite"))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        if not tables or len(tables) > 12:
            raise CompetitionSQLError("A fixture must have between one and twelve tables.")
        for (table,) in tables:
            escaped = table.replace('"', '""')
            if conn.execute(f'SELECT COUNT(*) FROM "{escaped}"').fetchone()[0] > 2000:
                raise CompetitionSQLError("Each fixture table is limited to 2,000 records.")
        conn.commit()
        conn.close()
        conn = None
        if os.path.getsize(temporary) > 5_000_000:
            raise CompetitionSQLError("Fixture database exceeds the size limit.")
        # Concurrent writers produce identical immutable content. No consumer ever
        # opens a partially built database; existing files need no replacement.
        if not target.exists():
            try:
                os.replace(temporary, target)
            except PermissionError:
                if not target.exists():
                    raise
        return target
    except sqlite3.Error as exc:
        raise CompetitionSQLError(f"Fixture creation failed: {exc}") from exc
    finally:
        if conn:
            conn.close()
        if os.path.exists(temporary):
            os.unlink(temporary)


def execute(schema: str, seed: str, sql: str, *, preview=False, deadline=None) -> dict:
    started = time.monotonic()
    conn = None
    try:
        tree = parse_select(sql)
        # SQLite's current clock would make reference/fault/repair disagree over
        # time. Authors must supply a fixed date literal instead.
        for node in tree.walk():
            if isinstance(node, (exp.CurrentDate, exp.CurrentTimestamp, exp.CurrentTime)):
                raise CompetitionSQLError("Use a fixed date/time value in competition queries.")
            if isinstance(node, exp.Literal) and node.is_string and node.this.lower() == "now":
                raise CompetitionSQLError("Use a fixed date/time value in competition queries.")
        path = fixture_path(schema, seed)
        seconds = min(settings.COMPETITION_QUERY_SECONDS, (deadline - time.monotonic()) if deadline else settings.COMPETITION_QUERY_SECONDS)
        if seconds <= 0:
            raise CompetitionSQLError("The judging time limit was reached. Try again.")
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        _limits(conn)
        conn.execute("PRAGMA query_only=ON")
        attach_deadline(conn, seconds, grace_seconds=0)
        conn.set_authorizer(_authorizer)
        cursor = conn.execute(sql)
        columns = [x[0] for x in cursor.description or []]
        limit = 200 if preview else 2000
        rows = cursor.fetchmany(limit + 1)
        truncated = len(rows) > limit
        rows = [list(row) for row in rows[:limit]]
        if any(isinstance(v, bytes) or isinstance(v, float) and not math.isfinite(v) for row in rows for v in row):
            raise CompetitionSQLError("Binary or non-finite query output is not supported.")
        if len(json.dumps(rows, ensure_ascii=False).encode()) > 1_000_000:
            raise CompetitionSQLError("Query output exceeds the 1 MB limit.")
        if truncated and not preview:
            raise CompetitionSQLError("Query output exceeds the judging row limit.")
        return {"success": True, "columns": columns, "rows": rows, "truncated": truncated,
                "execution_time_ms": round((time.monotonic() - started) * 1000, 2), "error": None}
    except (CompetitionSQLError, sqlite3.Error, sqlglot.errors.SqlglotError) as exc:
        return {"success": False, "columns": [], "rows": [], "truncated": False,
                "execution_time_ms": round((time.monotonic() - started) * 1000, 2), "error": str(exc)[:500]}
    finally:
        if conn:
            conn.close()


def public_database(schema, seed):
    path = fixture_path(schema, seed)
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        tables = []
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            escaped = name.replace('"', '""')
            columns = [{"name": r[1], "type": r[2], "primary_key": bool(r[5])} for r in conn.execute(f'PRAGMA table_info("{escaped}")')]
            rows = [list(row) for row in conn.execute(f'SELECT * FROM "{escaped}" LIMIT 100')]
            tables.append({"name": name, "columns": columns, "rows": rows})
        return tables
    finally:
        conn.close()
