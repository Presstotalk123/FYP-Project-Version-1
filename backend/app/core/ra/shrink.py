"""Make a counterexample as small and readable as possible.

Given a database on which two answers differ, ``shrink`` removes tuples one at a time,
keeping each removal only if the answers still differ, until no single tuple can go
(a simple form of delta debugging, Zeller 2002). The student then sees, say, three
tuples instead of thirty, which usually makes the mistake obvious.

``prettify`` replaces the made-up values of a solver's counterexample ("!0!", -31714 …)
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
    """Swap a solver's made-up values for readable ones, keeping the counterexample.

    The solver picks whatever satisfies the logic: strings such as "" or "!0!", numbers
    such as -31714. Strings become ``Attribute_1``, ``Attribute_2`` … and numbers small
    whole numbers, keeping equal values equal and numbers in the same order relative to
    each other and to the answers' constants (``avoid``), which are never changed. Each
    of the two swaps is kept only if the answers still differ on the result."""
    for swap in (_readable_strings, _readable_numbers):
        mapping = swap(db, avoid)
        if not mapping:
            continue
        trial = db.with_rows({t.name: [tuple(mapping.get(_key(v), v) for v in r) for r in t.rows]
                              for t in db.tables})
        if differs(trial):
            db = trial
    return db


def _key(v):
    return (type(v) is str, v)


def _readable_strings(db: Database, avoid: set) -> Dict[tuple, object]:
    mapping: Dict[tuple, object] = {}
    taken = {v for v in avoid if isinstance(v, str)}
    counters: Dict[str, int] = {}
    for t in db.tables:
        for row in t.rows:
            for col, v in zip(t.column_names, row):
                if not isinstance(v, str) or v in avoid or _key(v) in mapping:
                    continue
                n = counters.get(col, 0)
                while True:
                    n += 1
                    candidate = f"{col}_{n}"
                    if candidate not in taken:
                        break
                counters[col] = n
                taken.add(candidate)
                mapping[_key(v)] = candidate
    return mapping


def _readable_numbers(db: Database, avoid: set) -> Dict[tuple, object]:
    """Renumber 1, 2, 3 … in order, jumping over the constants so order is kept."""
    fixed = sorted(v for v in avoid if isinstance(v, (int, float)) and not isinstance(v, bool))
    values = sorted({v for t in db.tables for r in t.rows for v in r
                     if isinstance(v, (int, float)) and not isinstance(v, bool) and v not in fixed})
    if not values:
        return {}
    mapping: Dict[tuple, object] = {}
    last = 0
    for v in values:
        below = [c for c in fixed if c < v]
        above = [c for c in fixed if c > v]
        new = max(last + 1, (int(below[-1]) + 1) if below else 1)
        if above and new >= above[0]:
            return {}                                 # no whole number fits in between: keep them all
        mapping[_key(v)] = new
        last = new
    return mapping


def describe(db: Database) -> Dict[str, dict]:
    """The non-empty relations, as the website shows them."""
    return {t.name: {"columns": t.column_names, "rows": [list(r) for r in t.rows]}
            for t in db.tables if t.rows}


