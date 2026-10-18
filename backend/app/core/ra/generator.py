"""Generate small test databases from a schema alone (no question data needed).

How values are chosen
  * Every attribute gets a small **pool** of values (3 by default). Few values on
    purpose: with 0–5 tuples per relation drawn from 3 values, ties ("two students share
    the lowest GPA"), repeats and "some but not all" cases happen all the time.
  * Attributes with the **same name** share one pool (Sid in STUDENT, MAJOR and ENROLL),
    so natural joins find matches. So do attributes linked by a **foreign key**, and
    attributes **compared with each other** in either answer (σ A.x = B.y).
  * Every **constant** in either answer joins the pool of the attribute it is compared
    with ('Civil Engineering' joins Dname's pool), and for <, ≤, >, ≥ so do its
    neighbours (Numphds < 50 adds 49, 50 and 51), so each condition can come out
    both true and false and the boundary is tested.
  * Text values are readable placeholders (Sname_1, Sname_2), numbers small integers.

How databases are built
  * Relations are filled parents-first; a foreign-key attribute usually takes a value
    the parent relation already has, so joins along keys match.
  * Every generated tuple is inserted into a private SQLite copy of the staff schema and
    kept only if SQLite accepts it, so primary keys, NOT NULL, foreign keys and any
    CHECK constraint hold. Staff state a question's assumptions as CHECK constraints
    (Tutorial 5.5 Q3: CHECK ("teamid-one" < "teamid-two")).
  * NULLs are off by default: the course's questions assume complete data, and with
    NULLs, correct textbook answers (e.g. "lowest GPA" by difference instead of γ MIN)
    stop agreeing. A question can switch them on.

Everything is driven by one ``random.Random``, seeded per question, so every student's
answer meets exactly the same databases.
"""
import random
import sqlite3
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from app.core.ra import ast
from app.core.ra.schema import Database, Row, Table

_NUMERIC = ("INTEGER", "REAL", "NUMERIC")
# Relation sizes 0..5, weighted towards 2–4 tuples.
_SIZE_WEIGHTS = (1, 2, 3, 3, 2, 1)


@dataclass(frozen=True)
class GenConfig:
    pool_size: int = 3
    max_rows: int = 5
    null_rate: float = 0.0          # chance a nullable attribute is NULL
    fk_follow_rate: float = 0.85    # chance a foreign-key value is taken from the parent


# ── what the answers tell us about values ─────────────────────────────────────
@dataclass
class Hints:
    constants: Dict[str, List[Tuple[str, object]]]   # attribute name (casefolded) -> [(op, value)]
    loose_constants: List[Tuple[str, object]]         # constants whose attribute we could not place
    links: List[Tuple[str, str]]                      # attribute names compared with each other


def collect_hints(programs: Iterable[ast.Program]) -> Hints:
    hints = Hints({}, [], [])
    for program in programs:
        for stmt in program.statements:
            _walk_expr(stmt.expr, hints)
    return hints


def _walk_expr(e, hints: Hints) -> None:
    if isinstance(e, ast.Select):
        _walk_cond(e.condition, hints)
    if isinstance(e, ast.Binary) and e.condition is not None:
        _walk_cond(e.condition, hints)
    for child in ast.children(e):
        _walk_expr(child, hints)


def _walk_cond(c, hints: Hints) -> None:
    if isinstance(c, ast.BoolOp):
        _walk_cond(c.left, hints)
        _walk_cond(c.right, hints)
    elif isinstance(c, ast.Not):
        _walk_cond(c.operand, hints)
    elif isinstance(c, ast.Comparison):
        left, right = c.left, c.right
        if isinstance(left, ast.AttrRef) and isinstance(right, ast.AttrRef):
            hints.links.append((left.name.casefold(), right.name.casefold()))
        elif isinstance(left, ast.AttrRef) and isinstance(right, ast.Literal):
            hints.constants.setdefault(left.name.casefold(), []).append((c.op, right.value))
        elif isinstance(right, ast.AttrRef) and isinstance(left, ast.Literal):
            hints.constants.setdefault(right.name.casefold(), []).append((_flip(c.op), left.value))
        else:
            for side in (left, right):
                if isinstance(side, ast.Literal):
                    hints.loose_constants.append((c.op, side.value))


def _flip(op: str) -> str:
    return {"<": ">", ">": "<", "<=": ">=", ">=": "<="}.get(op, op)


# ── value pools ───────────────────────────────────────────────────────────────
class _UnionFind:
    def __init__(self):
        self.parent: Dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        self.parent[self.find(a)] = self.find(b)


def _neighbours(op: str, v) -> List[object]:
    if op not in ("<", "<=", ">", ">=") or isinstance(v, bool) or not isinstance(v, (int, float)):
        return [v]
    step = 1 if isinstance(v, int) else 0.5
    return [v - step, v, v + step]


class Pools:
    """One pool of candidate values per class of attributes that share values."""

    def __init__(self, db: Database, hints: Hints, config: GenConfig):
        uf = _UnionFind()
        names = {c.casefold() for t in db.tables for c in t.column_names}
        for t in db.tables:
            for c in t.column_names:
                uf.find(c.casefold())
            for fk in t.foreign_keys:
                for a, b in zip(fk.columns, fk.ref_columns):
                    uf.union(a.casefold(), b.casefold())
        for a, b in hints.links:
            if a in names and b in names:
                uf.union(a, b)
        self._class = {n: uf.find(n) for n in names}

        # Type and display name of each class come from the first attribute in it.
        kinds: Dict[str, str] = {}
        labels: Dict[str, str] = {}
        for t in db.tables:
            for c, affinity in t.columns:
                k = self._class[c.casefold()]
                kinds.setdefault(k, "number" if affinity in _NUMERIC else "text")
                labels.setdefault(k, c)
        self.kind = kinds

        pools: Dict[str, List[object]] = {}
        for k, kind in kinds.items():
            base = list(range(1, config.pool_size + 1)) if kind == "number" else \
                [f"{labels[k]}_{i}" for i in range(1, config.pool_size + 1)]
            pools[k] = base
        for name, consts in hints.constants.items():
            k = self._class.get(name)
            targets = [k] if k else [c for c in pools]           # a renamed attribute: try everywhere
            for op, v in consts:
                for target in targets:
                    self._add(pools, target, op, v)
        for op, v in hints.loose_constants:
            for target in pools:
                self._add(pools, target, op, v)
        self.pools = {k: list(dict.fromkeys(v)) for k, v in pools.items()}

    def _add(self, pools: Dict[str, List[object]], k: str, op: str, v) -> None:
        is_number = isinstance(v, (int, float)) and not isinstance(v, bool)
        if (self.kind[k] == "number") != is_number:
            return
        pools[k].extend(_neighbours(op, v))

    def pool_for(self, column: str) -> List[object]:
        return self.pools[self._class[column.casefold()]]


# ── databases ─────────────────────────────────────────────────────────────────
class Generator:
    def __init__(self, db: Database, programs: Sequence[ast.Program], config: GenConfig = GenConfig()):
        self.db = db
        self.config = config
        self.pools = Pools(db, collect_hints(programs), config)
        self.order = _parents_first(db.tables)
        self._conn = _validator(db)

    def close(self) -> None:
        self._conn.close()

    def generate(self, rng: random.Random, max_rows: Optional[int] = None) -> Database:
        """One random database that satisfies every constraint of the schema."""
        max_rows = self.config.max_rows if max_rows is None else max_rows
        weights = _SIZE_WEIGHTS[:max_rows + 1] if max_rows <= 5 else None
        conn = self._conn
        conn.execute("SAVEPOINT gen")
        try:
            kept: Dict[str, List[Row]] = {}
            for table in self.order:
                target = rng.choices(range(len(weights)), weights)[0] if weights else rng.randint(0, max_rows)
                placeholders = ", ".join("?" for _ in table.columns)
                sql = f'INSERT INTO "{table.name}" VALUES ({placeholders})'
                for _ in range(target * 2):            # extra tries: some rows break a key or CHECK
                    if len(kept.get(table.name, [])) >= target:
                        break
                    row = self._row(table, kept, rng)
                    try:
                        conn.execute(sql, row)
                    except sqlite3.Error:
                        continue
                    kept.setdefault(table.name, []).append(row)
            rows = {t.name: [tuple(r) for r in conn.execute(f'SELECT * FROM "{t.name}"')] for t in self.db.tables}
        finally:
            conn.execute("ROLLBACK TO gen")
            conn.execute("RELEASE gen")
        return self.db.with_rows(rows)

    def _row(self, table: Table, kept: Dict[str, List[Row]], rng: random.Random) -> Row:
        values: Dict[str, object] = {}
        for fk in table.foreign_keys:
            parent = self.db.lookup(fk.ref_table)
            parent_rows = kept.get(parent.name, []) if parent else []
            if parent_rows and rng.random() < self.config.fk_follow_rate:
                chosen = rng.choice(parent_rows)
                cols = parent.column_names
                for c, rc in zip(fk.columns, fk.ref_columns):
                    values[c] = chosen[cols.index(rc)]
        nullable = {c for c in table.column_names if c not in table.not_null}
        row = []
        for c in table.column_names:
            if c in values:
                row.append(values[c])
            elif c in nullable and self.config.null_rate and rng.random() < self.config.null_rate:
                row.append(None)
            else:
                row.append(rng.choice(self.pools.pool_for(c)))
        return tuple(row)


def _parents_first(tables: Sequence[Table]) -> List[Table]:
    by_name = {t.name.casefold(): t for t in tables}
    done, out = set(), []

    def visit(t: Table, path: frozenset) -> None:
        key = t.name.casefold()
        if key in done or key in path:
            return
        for fk in t.foreign_keys:
            parent = by_name.get(fk.ref_table.casefold())
            if parent is not None:
                visit(parent, path | {key})
        done.add(key)
        out.append(t)

    for t in tables:
        visit(t, frozenset())
    return out


def _validator(db: Database) -> sqlite3.Connection:
    """An empty in-memory copy of the schema that enforces its constraints."""
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.execute("PRAGMA foreign_keys = ON")
    for t in _parents_first(db.tables):
        conn.execute(t.create_sql or _create_sql(t))
    return conn


def _create_sql(t: Table) -> str:
    """For tables built in code (Database.from_dict), which have no CREATE TABLE text."""
    cols = ", ".join(f'"{c}" {ty}' for c, ty in t.columns)
    key = f', PRIMARY KEY ({", ".join(chr(34) + c + chr(34) for c in t.primary_key)})' if t.primary_key else ""
    return f'CREATE TABLE "{t.name}" ({cols}{key})'
