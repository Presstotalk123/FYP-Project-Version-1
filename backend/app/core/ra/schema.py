"""The relations an RA answer runs against: a schema, optionally with data.

RA questions are written as SQL: staff paste ``CREATE TABLE`` statements (the schema)
and, optionally, ``INSERT`` statements (the sample data). Both run once in a private
in-memory SQLite database, which is then read into plain Python tables. Nothing about
the answer itself ever touches SQLite: the evaluator works on these tables directly.

The schema keeps what the data generator needs later: column types, the primary key,
NOT NULL columns and foreign keys.
"""
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.core.ra import errors as E
from app.core.ra.errors import RAError

Row = Tuple[Any, ...]

MAX_SQL_CHARS = 100_000
MAX_ROWS_PER_TABLE = 5_000
# SQLite calls the progress handler every N virtual-machine steps; returning non-zero
# aborts the statement. This bounds how long staff SQL may run (recursive CTEs etc.).
_PROGRESS_STEPS = 10_000
_MAX_PROGRESS_CALLS = 2_000


@dataclass
class ForeignKey:
    columns: List[str]
    ref_table: str
    ref_columns: List[str]


@dataclass
class Table:
    name: str
    columns: List[Tuple[str, str]]          # (name, affinity)
    rows: List[Row]
    create_sql: str = ""
    primary_key: List[str] = field(default_factory=list)
    not_null: List[str] = field(default_factory=list)
    foreign_keys: List[ForeignKey] = field(default_factory=list)

    @property
    def column_names(self) -> List[str]:
        return [c for c, _ in self.columns]


class Database:
    def __init__(self, tables: Sequence[Table]):
        self.tables = list(tables)
        self._by_name = {t.name.casefold(): t for t in self.tables}

    def lookup(self, name: str) -> Optional[Table]:
        return self._by_name.get(name.casefold())

    @property
    def table_names(self) -> List[str]:
        return sorted(t.name for t in self.tables)

    def names(self) -> List[str]:
        """Every relation and attribute name, for the parser (see normalize.py)."""
        out = [t.name for t in self.tables]
        for t in self.tables:
            out.extend(t.column_names)
        return out

    def with_rows(self, rows: Dict[str, List[Row]]) -> "Database":
        """Same schema, different data (used for generated test databases)."""
        return Database([Table(t.name, t.columns, list(rows.get(t.name, [])), t.create_sql,
                               t.primary_key, t.not_null, t.foreign_keys)
                         for t in self.tables])

    def to_dict(self) -> List[dict]:
        return [{"name": t.name, "columns": t.column_names, "types": [ty for _, ty in t.columns],
                 "primary_key": t.primary_key, "rows": [list(r) for r in t.rows]}
                for t in self.tables]

    @classmethod
    def from_sql(cls, schema_sql: str, data_sql: str = "") -> "Database":
        """Run staff-written CREATE TABLE / INSERT SQL privately and read the result."""
        if len(schema_sql) + len(data_sql or "") > MAX_SQL_CHARS:
            raise RAError(E.INVALID_SCHEMA, f"The schema and data SQL are too long (max {MAX_SQL_CHARS:,} characters).")
        conn = sqlite3.connect(":memory:")
        try:
            conn.set_authorizer(_authorizer)
            calls = [0]

            def progress() -> int:
                calls[0] += 1
                return 1 if calls[0] > _MAX_PROGRESS_CALLS else 0
            conn.set_progress_handler(progress, _PROGRESS_STEPS)
            for label, sql in (("schema", schema_sql), ("data", data_sql or "")):
                if not sql.strip():
                    continue
                try:
                    conn.executescript(sql)
                except sqlite3.Error as e:
                    raise RAError(E.INVALID_SCHEMA, f"The {label} SQL could not be run: {e}.") from None
            conn.set_authorizer(None)
            return cls(_read_tables(conn))
        finally:
            conn.close()

    @classmethod
    def from_dict(cls, tables: Dict[str, Tuple[List[str], List[Row]]]) -> "Database":
        """{"Quiz1": (["Name", "Score"], [("Alice", 70), …])} — handy in tests."""
        out = []
        for name, (cols, rows) in tables.items():
            types = []
            for i, c in enumerate(cols):
                sample = next((r[i] for r in rows if r[i] is not None), None)
                types.append("TEXT" if isinstance(sample, str) else "NUMERIC")
            out.append(Table(name, list(zip(cols, types)), [tuple(r) for r in rows]))
        return cls(out)


def _authorizer(action, arg1, arg2, dbname, source):
    # Staff SQL only needs to create tables and insert rows. Never let it reach the
    # file system (ATTACH) or change connection settings (PRAGMA).
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_PRAGMA):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _read_tables(conn: sqlite3.Connection) -> List[Table]:
    tables = []
    for name, sql in conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY rowid"):
        info = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
        cols = [(r[1], affinity(r[2])) for r in info]
        pk = [r[1] for r in sorted((r for r in info if r[5]), key=lambda r: r[5])]
        # A key attribute can never be NULL in the relational model, whatever SQLite allows.
        not_null = [r[1] for r in info if r[3] or r[5]]
        fks: Dict[int, ForeignKey] = {}
        for fk in conn.execute(f'PRAGMA foreign_key_list("{name}")').fetchall():
            entry = fks.setdefault(fk[0], ForeignKey([], fk[2], []))
            entry.columns.append(fk[3])
            entry.ref_columns.append(fk[4])
        count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        if count > MAX_ROWS_PER_TABLE:
            raise RAError(E.INVALID_SCHEMA, f"Table {name} has {count:,} rows; the limit is {MAX_ROWS_PER_TABLE:,}.")
        rows = [tuple(_plain(v) for v in r) for r in conn.execute(f'SELECT * FROM "{name}"')]
        tables.append(Table(name, cols, rows, sql or "", pk, not_null, list(fks.values())))
    if not tables:
        raise RAError(E.INVALID_SCHEMA, "The schema SQL does not create any tables.")
    return tables


def _plain(v):
    return v.hex() if isinstance(v, bytes) else v


def affinity(declared: Optional[str]) -> str:
    """SQLite's column-affinity rules (https://sqlite.org/datatype3.html §3.1)."""
    t = (declared or "").upper()
    if "INT" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"
