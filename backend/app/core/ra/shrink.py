"""Make a counterexample as small and readable as possible.

Given a database on which two answers differ, ``shrink`` removes tuples one at a time,
keeping each removal only if the answers still differ, until no single tuple can go
(a simple form of delta debugging, Zeller 2002). The student then sees, say, three
tuples instead of thirty, which usually makes the mistake obvious.

``prettify`` replaces the made-up values of a proof's canonical database (⟨v1⟩, ⟨v2⟩ …)
with readable ones (Sid_1, 7 …), keeping equal values equal, and keeps the result only
if the answers still differ on it.
"""
from typing import Callable, Dict, List

from app.core.ra.schema import Database

MAX_CHECKS = 400


def shrink(db: Database, differs: Callable[[Database], bool], max_checks: int = MAX_CHECKS) -> Database:
    rows: Dict[str, List[tuple]] = {t.name: list(t.rows) for t in db.tables}
    checks = 0
    changed = True
    while changed and checks < max_checks:
        changed = False
        for name in list(rows):
            i = 0
            while i < len(rows[name]) and checks < max_checks:
                trial = dict(rows)
                trial[name] = rows[name][:i] + rows[name][i + 1:]
                checks += 1
                if differs(db.with_rows(trial)):
                    rows = trial
                    changed = True
                else:
                    i += 1
    return db.with_rows(rows)


def prettify(db: Database, differs: Callable[[Database], bool], avoid: set = frozenset()) -> Database:
    """Swap ⟨vN⟩ placeholders for readable values of the right type."""
    mapping: Dict[str, object] = {}
    next_number = 1
    counters: Dict[str, int] = {}
    for t in db.tables:
        for row in t.rows:
            for (col, affinity), v in zip(t.columns, row):
                if not (isinstance(v, str) and v.startswith("⟨v")) or v in mapping:
                    continue
                if affinity in ("INTEGER", "REAL", "NUMERIC"):
                    while next_number in avoid:
                        next_number += 1
                    mapping[v] = next_number
                    next_number += 1
                else:
                    counters[col] = counters.get(col, 0) + 1
                    candidate = f"{col}_{counters[col]}"
                    while candidate in avoid:
                        counters[col] += 1
                        candidate = f"{col}_{counters[col]}"
                    mapping[v] = candidate
    if not mapping:
        return db
    pretty = db.with_rows({t.name: [tuple(mapping.get(v, v) if isinstance(v, str) else v for v in r)
                                    for r in t.rows] for t in db.tables})
    return pretty if differs(pretty) else db


def describe(db: Database) -> Dict[str, dict]:
    """The non-empty relations, as the website shows them."""
    return {t.name: {"columns": t.column_names, "rows": [list(r) for r in t.rows]}
            for t in db.tables if t.rows}


