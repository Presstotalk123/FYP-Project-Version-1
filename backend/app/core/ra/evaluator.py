"""Evaluate relational algebra directly — no translation to SQL.

The semantics follow the course slides (CZ2007/SC2207 Topic 5), not SQL:

  * σ, Π, ×, ⋈, ρ, γ work on *bags*: Π keeps duplicate tuples (the slides show
    “Bob, Bob” after Π Name Grades); δ removes them.
  * ∪, ∩, − and ÷ remove duplicates (“duplicate tuples are automatically removed”).
  * ∪, ∩, − need both sides to have the same *set of attribute names* and match
    columns by name, not position (the tutorial renames with ρ before ∪).
  * Natural join keeps each common attribute once; θ-join keeps every attribute,
    so Quiz1.Name and Quiz2.Name both survive and must be qualified.
  * An assigned relation (R1 := …) is a copy with a new name: its attributes are
    qualified by R1 afterwards (Quiz1 ⋈ Quiz1.Score > R1.Score R1).
  * Conditions use three-valued logic, as SQL does: a comparison with NULL is
    *unknown*, NOT unknown is still unknown, and σ / θ-joins keep only tuples whose
    condition is *true*. (NULLs appear after outer joins, lecture 3.)
  * Aggregates ignore NULLs by default, as SQL does: COUNT(attr) skips them and
    SUM/AVG/MIN/MAX of nothing is NULL. Lecture 3 slides 20–21 instead count the NULL
    and show SUM of a NULL as 0; ``EvalOptions(aggregate_nulls="slides")`` follows
    the slides until the course confirms which rule it wants. With no grouping
    attributes, γ over an empty relation gives one tuple (COUNT = 0).
  * Outer joins pad missing values with NULL (None).

Every node's intermediate result is recorded in a trace so the website can show the
steps the way the slides do (R1, R2, R3 …).
"""
import difflib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Sequence, Tuple

from app.core.ra import ast
from app.core.ra import errors as E
from app.core.ra.errors import RAError
from app.core.ra.schema import Database, Row

MAX_INTERMEDIATE_ROWS = 200_000
# θ-joins test every pair of tuples; this caps the pairs tested (the work), not the
# rows kept, so a join of two large relations fails fast instead of hanging a worker.
MAX_PAIRS = 2_000_000
TRACE_ROWS = 50
_SYMBOL = {"product": "×", "natural_join": "⋈", "theta_join": "⋈", "left_join": "⟕",
           "right_join": "⟖", "full_join": "⟗", "union": "∪", "intersect": "∩",
           "difference": "−", "division": "÷"}


@dataclass(frozen=True)
class EvalOptions:
    # "sql": aggregates ignore NULLs (COUNT(attr) skips them, SUM of nothing is NULL).
    # "slides": COUNT(attr) counts every tuple and SUM of nothing is 0 (lecture 3, slides 20–21).
    aggregate_nulls: str = "sql"


# ── relations produced during evaluation ──────────────────────────────────────
@dataclass(frozen=True)
class Attr:
    name: str
    quals: FrozenSet[str]          # relation names this attribute can be qualified with
    type: str = "NUMERIC"

    def qualified(self) -> str:
        return f"{sorted(self.quals)[0]}.{self.name}" if self.quals else self.name


@dataclass
class Rel:
    attrs: List[Attr]
    rows: List[Row]

    @property
    def labels(self) -> List[str]:
        return make_labels(self.attrs)


def make_labels(attrs: Sequence[Attr]) -> List[str]:
    """Column headings: the bare name when unique, otherwise Qualifier.name."""
    labels = []
    for a in attrs:
        same = [b for b in attrs if b.name.casefold() == a.name.casefold()]
        if len(same) == 1:
            labels.append(a.name)
            continue
        others = set().union(*(b.quals for b in same if b is not a))
        own = sorted(a.quals - others) or sorted(a.quals)
        labels.append(f"{own[0]}.{a.name}" if own else a.name)
    return labels


def _distinct(rows: List[Row]) -> List[Row]:
    return list(dict.fromkeys(rows))


@dataclass
class EvalResult:
    columns: List[str]
    rows: List[Row]
    statements: List[dict]                 # [{"name": "R1" | None, "tree": {...}}]
    warnings: List[RAError] = field(default_factory=list)
    relation: Optional[Rel] = None


# ── values and conditions ─────────────────────────────────────────────────────
def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _compare(a, op: str, b) -> Optional[bool]:
    if a is None or b is None:
        return None                         # comparisons with NULL are unknown
    if _is_number(a) and _is_number(b) or isinstance(a, str) and isinstance(b, str):
        if op == "=":
            return a == b
        if op == "<>":
            return a != b
        if op == "<":
            return a < b
        if op == "<=":
            return a <= b
        if op == ">":
            return a > b
        return a >= b
    return op == "<>"                       # different types: never equal, never ordered


def _arith(a, op: str, b):
    if a is None or b is None or not (_is_number(a) and _is_number(b)):
        return None
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    return None if b == 0 else a / b


def _and(a: Optional[bool], b: Optional[bool]) -> Optional[bool]:
    if a is False or b is False:
        return False
    return None if a is None or b is None else True


def _or(a: Optional[bool], b: Optional[bool]) -> Optional[bool]:
    if a is True or b is True:
        return True
    return None if a is None or b is None else False


def _not(a: Optional[bool]) -> Optional[bool]:
    return None if a is None else not a


class Evaluator:
    def __init__(self, db: Database, max_rows: int = MAX_INTERMEDIATE_ROWS, trace: bool = True,
                 options: EvalOptions = EvalOptions()):
        self.db = db
        self.max_rows = max_rows
        self.trace = trace
        self.options = options
        self.assigned: Dict[str, Tuple[str, Rel]] = {}
        self.warnings: List[RAError] = []

    # ── name resolution ───────────────────────────────────────────────────────
    def resolve(self, ref: ast.AttrRef, attrs: Sequence[Attr], where: str) -> int:
        name = ref.name.casefold()
        matches = [i for i, a in enumerate(attrs) if a.name.casefold() == name]
        if ref.qualifier:
            qual = ref.qualifier.casefold()
            in_scope = {q.casefold() for a in attrs for q in a.quals}
            if qual not in in_scope:
                scope = ", ".join(sorted({q for a in attrs for q in a.quals})) or "none"
                raise RAError(E.UNKNOWN_RELATION, f"“{ref.qualifier}” is not a relation available in {where}.",
                              ref.pos.line, ref.pos.col, f"Relations in scope: {scope}.")
            matches = [i for i in matches if qual in {q.casefold() for q in attrs[i].quals}]
        if not matches:
            available = ", ".join(make_labels(attrs))
            close = difflib.get_close_matches(ref.name, [a.name for a in attrs], n=1)
            hint = f"Did you mean “{close[0]}”?" if close else (
                "If you removed it with Π earlier, select before you project (see the lecture "
                "example “σ School = ‘SCSE’ (Π ID, Name Students)” — wrong).")
            raise RAError(E.UNKNOWN_ATTRIBUTE, f"Attribute “{ref}” is not in {where} ({available}).",
                          ref.pos.line, ref.pos.col, hint)
        if len(matches) > 1:
            options = " or ".join(attrs[i].qualified() for i in matches)
            raise RAError(E.AMBIGUOUS_ATTRIBUTE, f"“{ref}” is ambiguous in {where}: use {options}.",
                          ref.pos.line, ref.pos.col)
        return matches[0]

    def value_fn(self, v, attrs: Sequence[Attr], where: str) -> Tuple[Callable[[Row], Any], str]:
        """Compile a value to (row -> value, type)."""
        if isinstance(v, ast.AttrRef):
            i = self.resolve(v, attrs, where)
            return (lambda row, i=i: row[i]), attrs[i].type
        if isinstance(v, ast.Literal):
            kind = "STRING" if isinstance(v.value, str) else "NUMBER"
            return (lambda row, x=v.value: x), kind
        lf, _ = self.value_fn(v.left, attrs, where)
        rf, _ = self.value_fn(v.right, attrs, where)
        return (lambda row: _arith(lf(row), v.op, rf(row))), "NUMERIC"

    def cond_fn(self, c, attrs: Sequence[Attr], where: str) -> Callable[[Row], Optional[bool]]:
        """Compile a condition to row -> True / False / None (unknown)."""
        if isinstance(c, ast.BoolOp):
            lf, rf = self.cond_fn(c.left, attrs, where), self.cond_fn(c.right, attrs, where)
            if c.op == "AND":
                return lambda row: _and(lf(row), rf(row))
            return lambda row: _or(lf(row), rf(row))
        if isinstance(c, ast.Not):
            f = self.cond_fn(c.operand, attrs, where)
            return lambda row: _not(f(row))
        lf, lt = self.value_fn(c.left, attrs, where)
        rf, rt = self.value_fn(c.right, attrs, where)
        text_vs_number = ({lt, rt} & {"TEXT", "STRING"}) and ({lt, rt} & {"NUMBER", "INTEGER", "REAL"})
        if text_vs_number:
            self.warnings.append(RAError(E.TYPE_MISMATCH, f"“{c}” compares text with a number — is that intended?",
                                         c.pos.line, c.pos.col))
        op = c.op
        return lambda row: _compare(lf(row), op, rf(row))

    # ── evaluation ────────────────────────────────────────────────────────────
    def _check_size(self, count: int, e) -> None:
        if count > self.max_rows:
            hint = "Did you mean ⋈ instead of ×?" if isinstance(e, ast.Binary) and e.op == "product" else None
            raise RAError(E.RESULT_TOO_LARGE,
                          f"An intermediate result has more than {self.max_rows:,} tuples.",
                          e.pos.line, e.pos.col, hint)

    def _node(self, op: str, label: str, rel: Rel, kids: Sequence[dict], pos: ast.Pos) -> dict:
        if not self.trace:
            return {}
        return {"op": op, "label": label, "columns": rel.labels, "row_count": len(rel.rows),
                "rows": [list(r) for r in rel.rows[:TRACE_ROWS]], "children": list(kids),
                "line": pos.line, "col": pos.col}

    def eval(self, e) -> Tuple[Rel, dict]:
        if isinstance(e, ast.Relation):
            return self.relation(e)
        if isinstance(e, ast.Select):
            return self.select(e)
        if isinstance(e, ast.Project):
            return self.project(e)
        if isinstance(e, ast.Rename):
            return self.rename(e)
        if isinstance(e, ast.Distinct):
            child, t = self.eval(e.child)
            rel = Rel(child.attrs, _distinct(child.rows))
            return rel, self._node("distinct", "δ", rel, [t], e.pos)
        if isinstance(e, ast.Group):
            return self.group(e)
        if e.op in ("product", "theta_join"):
            return self.product(e)
        if e.op == "natural_join":
            return self.natural_join(e, outer=None)
        if e.op in ("left_join", "right_join", "full_join"):
            side = e.op.split("_")[0]
            return self.natural_join(e, outer=side) if e.condition is None else self.product(e, outer=side)
        if e.op in ("union", "intersect", "difference"):
            return self.set_op(e)
        return self.division(e)

    def relation(self, e: ast.Relation) -> Tuple[Rel, dict]:
        key = e.name.casefold()
        if key in self.assigned:
            name, rel = self.assigned[key]
            return rel, self._node("relation", name, rel, [], e.pos)
        table = self.db.lookup(e.name)
        if table is None:
            close = difflib.get_close_matches(e.name, self.db.table_names, n=1)
            raise RAError(E.UNKNOWN_RELATION,
                          f"Relation “{e.name}” does not exist. Available: {', '.join(self.db.table_names)}.",
                          e.pos.line, e.pos.col, f"Did you mean “{close[0]}”?" if close else None)
        attrs = [Attr(c, frozenset({table.name}), t) for c, t in table.columns]
        rel = Rel(attrs, list(table.rows))
        return rel, self._node("relation", table.name, rel, [], e.pos)

    def select(self, e: ast.Select) -> Tuple[Rel, dict]:
        child, t = self.eval(e.child)
        f = self.cond_fn(e.condition, child.attrs, "the input of σ")
        rel = Rel(child.attrs, [r for r in child.rows if f(r) is True])
        return rel, self._node("select", f"σ {e.condition}", rel, [t], e.pos)

    def project(self, e: ast.Project) -> Tuple[Rel, dict]:
        child, t = self.eval(e.child)
        fns, attrs = [], []
        for item in e.items:
            if isinstance(item.value, ast.AttrRef):
                i = self.resolve(item.value, child.attrs, "the input of Π")
                fns.append(lambda row, i=i: row[i])
                a = child.attrs[i]
                attrs.append(Attr(item.alias, frozenset(), a.type) if item.alias else a)
            else:
                f, _ = self.value_fn(item.value, child.attrs, "the input of Π")
                fns.append(f)
                attrs.append(Attr(item.alias or str(item.value), frozenset(), "NUMERIC"))
        labels = make_labels(attrs)
        dup = next((lbl for lbl in labels if [x.casefold() for x in labels].count(lbl.casefold()) > 1), None)
        if dup:
            raise RAError(E.DUPLICATE_ATTRIBUTE, f"“{dup}” appears twice in Π.", e.pos.line, e.pos.col)
        rel = Rel(attrs, [tuple(f(r) for f in fns) for r in child.rows])     # bag: duplicates kept
        return rel, self._node("project", f"Π {', '.join(str(i) for i in e.items)}", rel, [t], e.pos)

    def rename(self, e: ast.Rename) -> Tuple[Rel, dict]:
        child, t = self.eval(e.child)
        names = e.attributes or [a.name for a in child.attrs]
        if len(names) != len(child.attrs):
            raise RAError(E.RENAME_ARITY, f"ρ lists {len(names)} new attribute names but the relation has "
                          f"{len(child.attrs)} ({', '.join(child.labels)}).", e.pos.line, e.pos.col)
        folded = [n.casefold() for n in names]
        dup = next((n for n in names if folded.count(n.casefold()) > 1), None)
        if dup:
            raise RAError(E.DUPLICATE_ATTRIBUTE,
                          f"After ρ {e.relation} the relation would have two attributes called “{dup}”.",
                          e.pos.line, e.pos.col, f"List new, distinct names: ρ {e.relation}(…).")
        attrs = [Attr(n, frozenset({e.relation}), a.type) for n, a in zip(names, child.attrs)]
        rel = Rel(attrs, child.rows)
        shown = e.relation + (f"({', '.join(e.attributes)})" if e.attributes else "")
        return rel, self._node("rename", f"ρ {shown}", rel, [t], e.pos)

    def group(self, e: ast.Group) -> Tuple[Rel, dict]:
        child, t = self.eval(e.child)
        where = "the input of γ"
        keys = [self.resolve(g, child.attrs, where) for g in e.group_by]
        aggs = []
        for a in e.aggregates:
            if a.attr is None:
                if a.func != "COUNT":
                    raise RAError(E.INVALID_AGGREGATE, f"{a.func}(*) is not allowed; only COUNT(*).",
                                  a.pos.line, a.pos.col)
                aggs.append((a, None))
                continue
            i = self.resolve(a.attr, child.attrs, where)
            if a.func in ("SUM", "AVG") and child.attrs[i].type == "TEXT":
                raise RAError(E.INVALID_AGGREGATE, f"{a.func} needs a numeric attribute, but “{a.attr}” is text.",
                              a.pos.line, a.pos.col)
            aggs.append((a, i))
        groups: Dict[Row, List[Row]] = {}
        for r in child.rows:
            groups.setdefault(tuple(r[i] for i in keys), []).append(r)
        if not keys and not groups:
            groups[()] = []                  # γ COUNT(*) over an empty relation → one tuple
        rows = []
        slides = self.options.aggregate_nulls == "slides"
        for key, members in groups.items():
            out = list(key)
            for a, i in aggs:
                vals = [m[i] for m in members if m[i] is not None] if i is not None else members
                if a.func == "COUNT":
                    out.append(len(members) if slides else len(vals))
                elif not vals:
                    out.append(0 if slides and a.func == "SUM" else None)
                elif a.func == "SUM":
                    out.append(sum(vals))
                elif a.func == "AVG":
                    out.append(sum(vals) / len(vals))
                elif a.func == "MIN":
                    out.append(min(vals))
                else:
                    out.append(max(vals))
            rows.append(tuple(out))
        attrs = [child.attrs[i] for i in keys] + [
            Attr(a.alias, frozenset(), "INTEGER" if a.func == "COUNT" else "NUMERIC") for a, _ in aggs]
        labels = make_labels(attrs)
        dup = next((lbl for lbl in labels if [x.casefold() for x in labels].count(lbl.casefold()) > 1), None)
        if dup:
            raise RAError(E.DUPLICATE_ATTRIBUTE, f"“{dup}” appears twice in γ.", e.pos.line, e.pos.col)
        rel = Rel(attrs, rows)
        shown = ", ".join([str(g) for g in e.group_by] + [str(a) for a in e.aggregates])
        return rel, self._node("group", f"γ {shown}", rel, [t], e.pos)

    def _check_no_clash(self, left: Rel, right: Rel, e: ast.Binary) -> None:
        for la in left.attrs:
            for ra in right.attrs:
                if la.name.casefold() == ra.name.casefold() and la.quals & ra.quals:
                    both = sorted(la.quals & ra.quals)[0]
                    raise RAError(E.SAME_NAME_INPUTS,
                                  f"Both inputs of {_SYMBOL[e.op]} have an attribute {both}.{la.name}, "
                                  "so they could not be told apart.", e.pos.line, e.pos.col,
                                  "Give one input a new name first, e.g. R1 := Quiz1 or ρ Q2 Quiz1.")

    def product(self, e: ast.Binary, outer: Optional[str] = None) -> Tuple[Rel, dict]:
        left, lt = self.eval(e.left)
        right, rt = self.eval(e.right)
        self._check_no_clash(left, right, e)
        attrs = left.attrs + right.attrs
        pairs = len(left.rows) * len(right.rows)
        if e.condition is None:
            # Check the size before building it: a careless × of three tables could
            # otherwise allocate billions of tuples before any check ran.
            if pairs > self.max_rows:
                self._check_size(pairs, e)
            rows = [l + r for l in left.rows for r in right.rows]
            label = "×"
        else:
            sym = {"left": "⟕", "right": "⟖", "full": "⟗"}.get(outer, "⋈")
            if pairs > MAX_PAIRS:
                raise RAError(E.RESULT_TOO_LARGE,
                              f"This {sym} would compare {pairs:,} pairs of tuples, more than the "
                              f"limit of {MAX_PAIRS:,}.", e.pos.line, e.pos.col,
                              "Select or project the inputs first so they are smaller.")
            f = self.cond_fn(e.condition, attrs, f"the inputs of {sym}")
            matched_l, matched_r, rows = set(), set(), []
            for i, l in enumerate(left.rows):
                for j, r in enumerate(right.rows):
                    if f(l + r) is True:
                        rows.append(l + r)
                        matched_l.add(i)
                        matched_r.add(j)
                if len(rows) > self.max_rows:
                    break
            if outer in ("left", "full"):
                rows += [l + (None,) * len(right.attrs) for i, l in enumerate(left.rows) if i not in matched_l]
            if outer in ("right", "full"):
                rows += [(None,) * len(left.attrs) + r for j, r in enumerate(right.rows) if j not in matched_r]
            label = f"{sym} {e.condition}"
        self._check_size(len(rows), e)
        rel = Rel(attrs, rows)
        return rel, self._node(e.op, label, rel, [lt, rt], e.pos)

    def natural_join(self, e: ast.Binary, outer: Optional[str]) -> Tuple[Rel, dict]:
        left, lt = self.eval(e.left)
        right, rt = self.eval(e.right)
        rnames = {}
        for j, a in enumerate(right.attrs):
            rnames.setdefault(a.name.casefold(), []).append(j)
        common = [(i, rnames[a.name.casefold()]) for i, a in enumerate(left.attrs) if a.name.casefold() in rnames]
        for i, js in common:
            name = left.attrs[i].name
            if len(js) > 1 or sum(a.name.casefold() == name.casefold() for a in left.attrs) > 1:
                raise RAError(E.AMBIGUOUS_ATTRIBUTE,
                              f"⋈ would join on “{name}”, but an input has more than one attribute called “{name}”.",
                              e.pos.line, e.pos.col, "Use Π or ρ first so each input has one.")
        pairs = [(i, js[0]) for i, js in common]
        rcommon = {j for _, j in pairs}
        rkeep = [j for j in range(len(right.attrs)) if j not in rcommon]
        attrs = [Attr(a.name, a.quals | next((right.attrs[j].quals for i2, j in pairs if i2 == i), frozenset()), a.type)
                 for i, a in enumerate(left.attrs)] + [right.attrs[j] for j in rkeep]
        index: Dict[Row, List[int]] = {}
        for j, r in enumerate(right.rows):
            index.setdefault(tuple(r[jj] for _, jj in pairs), []).append(j)
        rows, matched_r = [], set()
        for l in left.rows:
            key = tuple(l[i] for i, _ in pairs)
            hits = [] if any(v is None for v in key) else index.get(key, [])
            for j in hits:
                rows.append(l + tuple(right.rows[j][jj] for jj in rkeep))
                matched_r.add(j)
            if not hits and outer in ("left", "full"):
                rows.append(l + (None,) * len(rkeep))
            if len(rows) > self.max_rows:
                break
        if outer in ("right", "full"):
            for j, r in enumerate(right.rows):
                if j in matched_r:
                    continue
                row = [None] * len(left.attrs)
                for i, jj in pairs:
                    row[i] = r[jj]               # common attributes take the right-hand value
                rows.append(tuple(row) + tuple(r[jj] for jj in rkeep))
        self._check_size(len(rows), e)
        rel = Rel(attrs, rows)
        return rel, self._node(e.op, _SYMBOL[e.op], rel, [lt, rt], e.pos)

    def set_op(self, e: ast.Binary) -> Tuple[Rel, dict]:
        left, lt = self.eval(e.left)
        right, rt = self.eval(e.right)
        llab, rlab = left.labels, right.labels
        lkeys, rkeys = [x.casefold() for x in llab], [x.casefold() for x in rlab]
        if sorted(lkeys) != sorted(rkeys) or len(set(lkeys)) != len(lkeys):
            raise RAError(E.UNION_INCOMPATIBLE,
                          f"The two sides of {_SYMBOL[e.op]} must have the same attributes: the left has "
                          f"({', '.join(llab)}), the right has ({', '.join(rlab)}).", e.pos.line, e.pos.col,
                          "Use Π (or ρ to rename) so both sides match. Remember that σ, Π and ρ apply only "
                          "to the relation right after them — add parentheses to apply them to more.")
        order = [rkeys.index(k) for k in lkeys]
        rrows = [tuple(r[i] for i in order) for r in right.rows]
        lset, rset = _distinct(left.rows), set(rrows)
        if e.op == "union":
            rows = _distinct(lset + rrows)
        elif e.op == "intersect":
            rows = [r for r in lset if r in rset]
        else:
            rows = [r for r in lset if r not in rset]
        rel = Rel(left.attrs, rows)
        return rel, self._node(e.op, _SYMBOL[e.op], rel, [lt, rt], e.pos)

    def division(self, e: ast.Binary) -> Tuple[Rel, dict]:
        left, lt = self.eval(e.left)
        right, rt = self.eval(e.right)
        lidx = {a.name.casefold(): i for i, a in enumerate(left.attrs)}
        ridx = {a.name.casefold(): i for i, a in enumerate(right.attrs)}
        if len(lidx) != len(left.attrs) or len(ridx) != len(right.attrs):
            raise RAError(E.INVALID_DIVISION, "÷ needs distinct attribute names on both sides.",
                          e.pos.line, e.pos.col)
        missing = [right.attrs[i].name for k, i in ridx.items() if k not in lidx]
        keep = [i for k, i in lidx.items() if k not in ridx]
        if missing or not keep:
            raise RAError(E.INVALID_DIVISION,
                          f"R1 ÷ R2 needs every attribute of R2 ({', '.join(right.labels)}) to be in R1 "
                          f"({', '.join(left.labels)}), and R1 to have at least one more.",
                          e.pos.line, e.pos.col,
                          f"{', '.join(missing)} is not in the left side — project it away first, e.g. "
                          f"R1 ÷ (Π … R2)." if missing else None)
        bcols = [lidx[k] for k in ridx]
        rorder = list(ridx.values())
        divisor = {tuple(r[i] for i in rorder) for r in right.rows}
        seen: Dict[Row, set] = {}
        for r in left.rows:
            seen.setdefault(tuple(r[i] for i in keep), set()).add(tuple(r[i] for i in bcols))
        rows = [a for a, bs in seen.items() if divisor <= bs]
        rel = Rel([left.attrs[i] for i in keep], rows)
        return rel, self._node("division", "÷", rel, [lt, rt], e.pos)

    # ── programs ──────────────────────────────────────────────────────────────
    def run(self, program: ast.Program) -> EvalResult:
        statements = []
        rel = None
        for s in program.statements:
            rel, tree = self.eval(s.expr)
            if s.name is not None:
                if self.db.lookup(s.name):
                    raise RAError(E.INVALID_ASSIGNMENT,
                                  f"“{s.name}” is already the name of a table; choose another name.",
                                  s.pos.line, s.pos.col)
                # An assigned relation is a renamed copy, so its attributes are qualified
                # by the new name (R1.Score). Attributes whose names repeat (after a
                # θ-join) also keep their old qualifier so they stay distinguishable.
                names = [a.name.casefold() for a in rel.attrs]
                rel = Rel([Attr(a.name, frozenset({s.name}) | (a.quals if names.count(a.name.casefold()) > 1
                                                               else frozenset()), a.type)
                           for a in rel.attrs], rel.rows)
                self.assigned[s.name.casefold()] = (s.name, rel)
            statements.append({"name": s.name, "tree": tree, "line": s.pos.line})
        return EvalResult(rel.labels, rel.rows, statements, self.warnings, rel)


def evaluate(program: ast.Program, db: Database, *, trace: bool = True,
             max_rows: int = MAX_INTERMEDIATE_ROWS, options: EvalOptions = EvalOptions()) -> EvalResult:
    return Evaluator(db, max_rows=max_rows, trace=trace, options=options).run(program)
