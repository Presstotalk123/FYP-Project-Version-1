"""Compare two relations the way the grader does.

Two results are the same answer when they have the same **attribute names** (in any
order, ignoring case) and the same tuples. Tuples are compared as a **set** by default,
so a missing final δ does not matter; a question can ask for **bag** comparison, where
duplicates count.

Numbers are compared by value (2 equals 2.0), and floats are rounded to 9 decimal
places first, so AVG computed in a different order still matches.
"""
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence, Tuple

Row = Tuple[Any, ...]


def _norm_value(v):
    if isinstance(v, float):
        r = round(v, 9)
        return int(r) if r.is_integer() else r
    return v


def norm_row(row: Sequence[Any]) -> Row:
    return tuple(_norm_value(v) for v in row)


def column_keys(columns: Sequence[str]) -> List[str]:
    return [c.casefold() for c in columns]


def same_columns(expected: Sequence[str], got: Sequence[str]) -> bool:
    e, g = column_keys(expected), column_keys(got)
    return len(e) == len(g) and sorted(e) == sorted(g)


def align(rows: Sequence[Row], from_columns: Sequence[str], to_columns: Sequence[str]) -> List[Row]:
    """Reorder ``rows`` (whose columns are ``from_columns``) into ``to_columns`` order."""
    src = column_keys(from_columns)
    order = [src.index(k) for k in column_keys(to_columns)]
    return [tuple(r[i] for i in order) for r in rows]


@dataclass
class Comparison:
    same_columns: bool
    equal: bool
    # Tuples the expected answer has and the student's lacks, and the reverse. In
    # expected-column order. Empty when the columns differ.
    missing: List[Row] = field(default_factory=list)
    extra: List[Row] = field(default_factory=list)


def compare(expected_columns: Sequence[str], expected_rows: Sequence[Row],
            got_columns: Sequence[str], got_rows: Sequence[Row], *, bag: bool = False) -> Comparison:
    if not same_columns(expected_columns, got_columns):
        return Comparison(False, False)
    exp = [norm_row(r) for r in expected_rows]
    got = [norm_row(r) for r in align(got_rows, got_columns, expected_columns)]
    if bag:
        ce, cg = Counter(exp), Counter(got)
        missing = list((ce - cg).elements())
        extra = list((cg - ce).elements())
    else:
        se, sg = set(exp), set(got)
        missing = [r for r in dict.fromkeys(exp) if r not in sg]
        extra = [r for r in dict.fromkeys(got) if r not in se]
    return Comparison(True, not missing and not extra, missing, extra)


def equal(expected_columns, expected_rows, got_columns, got_rows, *, bag: bool = False) -> bool:
    return compare(expected_columns, expected_rows, got_columns, got_rows, bag=bag).equal


def fingerprint(columns: Sequence[str], rows: Sequence[Row], *, bag: bool = False) -> Optional[tuple]:
    """A hashable summary that is equal exactly when ``compare`` says equal (same columns).

    Columns are put in sorted-name order so two results with the same attributes in a
    different order get the same fingerprint.
    """
    keys = column_keys(columns)
    order = sorted(range(len(keys)), key=lambda i: keys[i])
    reordered = [tuple(n[i] for i in order) for n in map(norm_row, rows)]
    body = tuple(sorted(Counter(reordered).items(), key=repr)) if bag else \
        tuple(sorted(set(reordered), key=repr))
    return tuple(sorted(keys)), body
