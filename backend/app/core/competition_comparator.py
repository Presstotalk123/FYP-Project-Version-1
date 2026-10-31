"""Typed positional comparison: duplicates and text whitespace are meaningful."""
from collections import Counter
from decimal import Decimal, InvalidOperation


def _cell(value):
    if value is None:
        return ("null", "")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return ("number", Decimal(str(value)))
    return (type(value).__name__, value)


def matches(actual: dict, approved: dict, *, order_sensitive=False, numeric_tolerance=0) -> bool:
    if not actual.get("success", True) or actual.get("truncated", False):
        return False
    if actual["columns"] != approved["columns"]:
        return False
    if any(len(row) != len(approved["columns"]) for row in approved["rows"] + actual["rows"]):
        return False
    left = [tuple(_cell(v) for v in row) for row in actual["rows"]]
    right = [tuple(_cell(v) for v in row) for row in approved["rows"]]
    if len(left) != len(right):
        return False
    if not numeric_tolerance:
        return left == right if order_sensitive else Counter(left) == Counter(right)
    if len(left) > 200:
        return False  # Also enforced on approved authoring outputs.
    tolerance = Decimal(str(numeric_tolerance))

    def same(a, b):
        try:
            return all(x == y or x[0] == y[0] == "number" and abs(x[1] - y[1]) <= tolerance for x, y in zip(a, b))
        except InvalidOperation:
            return False

    if order_sensitive:
        return all(same(a, b) for a, b in zip(left, right))
    # Bipartite matching avoids a greedy tolerance match consuming the only
    # compatible row for a later duplicate. Suites are capped at 2,000 rows.
    assigned = {}

    def augment(i, visited):
        for j, row in enumerate(right):
            if j not in visited and same(left[i], row):
                visited.add(j)
                if j not in assigned or augment(assigned[j], visited):
                    assigned[j] = i
                    return True
        return False

    return all(augment(i, set()) for i in range(len(left)))
