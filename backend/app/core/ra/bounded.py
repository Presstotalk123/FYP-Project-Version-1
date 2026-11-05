"""Search for a small database where two RA answers differ: every one, up to a size.

logic.py describes *all* databases with quantifiers, which is what a proof needs, but a
solver often can't build a counterexample from quantified formulas. Here the database
is finite and symbolic instead: each stored table has ``k`` tuple slots, and each slot is
an unknown tuple that may or may not be there. Every operator is then worked out on
those slots, as the evaluator would on real tuples (σ keeps a slot when its condition
holds, × pairs slots up, γ adds up the slots of a group …), so the formulas have no
quantifiers and Z3 decides them quickly — COUNT, SUM, AVG and duplicates included.

If Z3 finds values for the slots that make the answers differ, those tuples are the
counterexample; it is still checked with SQLite and the real evaluator before use
(equivalence.py). Finding none proves nothing beyond "no counterexample with at most k
tuples per table", which is why this is only the counterexample half of the prover.
"""
from typing import Dict, List, Optional, Sequence, Tuple

import z3

from app.core.ra import ast
from app.core.ra.compare import column_keys
from app.core.ra.errors import RAError
from app.core.ra.evaluator import Attr, Evaluator, EvalOptions, Rel
from app.core.ra.logic import Logic, Unsupported, _Translate
from app.core.ra.schema import Database, Table

MAX_SLOTS = 600            # tuple slots in any intermediate result

Slot = Tuple[z3.BoolRef, List[z3.ExprRef]]      # (is it there, its values)


class _Bounded(_Translate):
    """The evaluator over tuple slots: every relation is a list of (present, values)."""

    def __init__(self, logic: Logic, options: EvalOptions, k: int):
        super().__init__(logic, options)
        self.k = k
        self.base: Dict[str, List[Slot]] = {}
        self._b = 0

    def _flag(self) -> z3.BoolRef:
        self._b += 1
        return z3.Bool(f"p{self._b}", self.L.ctx)

    def _out(self, attrs: List[Attr], slots: List[Slot], e=None) -> Tuple[Rel, dict]:
        if len(slots) > MAX_SLOTS:
            raise Unsupported("too many tuple slots")
        return Rel(attrs, slots), {}

    @staticmethod
    def _slots(rel: Rel) -> List[Slot]:
        return rel.rows                                  # type: ignore[return-value]

    def _same(self, a: Sequence[z3.ExprRef], b: Sequence[z3.ExprRef]) -> z3.BoolRef:
        return self.L.all_of([x == y for x, y in zip(a, b)])

    def _distinct(self, slots: List[Slot]) -> List[Slot]:
        """Keep a slot only if no earlier slot that is there holds the same tuple."""
        out = []
        for i, (p, v) in enumerate(slots):
            earlier = [z3.And(q, self._same(w, v)) for q, w in slots[:i]]
            out.append((z3.And(p, z3.Not(self.L.any_of(earlier))) if earlier else p, v))
        return out

    def _contains(self, slots: List[Slot], v: Sequence[z3.ExprRef]) -> z3.BoolRef:
        return self.L.any_of([z3.And(q, self._same(w, v)) for q, w in slots])

    # ── the stored tables ─────────────────────────────────────────────────────
    def table_slots(self, t: Table) -> List[Slot]:
        key = t.name.casefold()
        if key not in self.base:
            self.L.table(t)
            self.base[key] = [(self._flag(), self.L.fresh_list(len(t.columns), f"{t.name}_")) for _ in range(self.k)]
        return self.base[key]

    def constraints(self) -> List[z3.BoolRef]:
        """The same rules as Logic.axioms, on the slots: types, no NULLs, distinct tuples,
        primary keys, foreign keys (parents get slots too)."""
        L = self.L
        pending = list(self.base)
        while pending:
            t = L.used[pending.pop()]
            for fk in t.foreign_keys:
                parent = self.db.lookup(fk.ref_table)
                if parent is not None and parent.name.casefold() not in self.base:
                    self.table_slots(parent)
                    pending.append(parent.name.casefold())
        out = []
        for key, slots in self.base.items():
            t = L.used[key]
            cols = t.column_names
            for i, (p, v) in enumerate(slots):
                out.append(z3.Implies(p, L.all_of([L._domain(t, c, aff, x) for (c, aff), x in zip(t.columns, v)])))
                for q, w in slots[:i]:
                    out.append(z3.Implies(z3.And(p, q), z3.Not(self._same(v, w))))          # a set
                    if t.primary_key and len(t.primary_key) < len(cols):
                        k = [cols.index(c) for c in t.primary_key]
                        out.append(z3.Implies(z3.And(p, q), z3.Not(self._same([v[j] for j in k], [w[j] for j in k]))))
                # Symmetry: fill the slots in order, so each database is searched once.
                if i:
                    out.append(z3.Implies(p, slots[i - 1][0]))
            for fk in t.foreign_keys:
                parent = self.db.lookup(fk.ref_table)
                if parent is None or any(c not in cols for c in fk.columns) \
                        or any(c not in parent.column_names for c in fk.ref_columns):
                    continue
                pcols = parent.column_names
                for p, v in slots:
                    out.append(z3.Implies(p, L.any_of([
                        z3.And(q, *[w[pcols.index(rc)] == v[cols.index(c)] for c, rc in zip(fk.columns, fk.ref_columns)])
                        for q, w in self.base[parent.name.casefold()]])))
        return out

    # ── operators ─────────────────────────────────────────────────────────────
    def eval(self, e):
        if isinstance(e, ast.Distinct):
            child, _ = self.eval(e.child)
            return self._out(child.attrs, self._distinct(self._slots(child)))
        if isinstance(e, ast.Binary) and e.op not in (
                "product", "theta_join", "natural_join", "left_join", "right_join", "full_join",
                "union", "intersect", "difference", "division"):
            raise Unsupported(e.op)
        return Evaluator.eval(self, e)

    def rename(self, e: ast.Rename):
        return Evaluator.rename(self, e)

    def relation(self, e: ast.Relation):
        key = e.name.casefold()
        if key in self.assigned:
            _name, rel = self.assigned[key]
            return rel, {}
        table = self.db.lookup(e.name)
        if table is None:
            return Evaluator.relation(self, e)
        attrs = [Attr(c, frozenset({table.name}), t) for c, t in table.columns]
        return self._out(attrs, list(self.table_slots(table)))

    def select(self, e: ast.Select):
        child, _ = self.eval(e.child)
        where = "the input of σ"
        self._check_condition(e.condition, child.attrs, where)
        return self._out(child.attrs, [(z3.And(p, self.condition(e.condition, child.attrs, v, where)[0]), v)
                                       for p, v in self._slots(child)])

    def project(self, e: ast.Project):
        child, _ = self.eval(e.child)
        indexes, _fns, attrs = self._project_plan(e, child)
        where = "the input of Π"
        out = []
        for p, v in self._slots(child):
            out.append((p, [v[i] if i is not None else self.term(item.value, child.attrs, v, where)
                            for i, item in zip(indexes, e.items)]))
        return self._out(attrs, out)

    def group(self, e: ast.Group):
        child, _ = self.eval(e.child)
        keys, aggs, attrs = self.group_plan(e, child)
        L = self.L
        slots = self._slots(child)
        slides = self.options.aggregate_nulls == "slides"
        groups: List[Tuple[z3.BoolRef, List[z3.ExprRef], List[z3.BoolRef]]] = []
        if keys:
            for i, (p, v) in enumerate(slots):
                key = [v[k] for k in keys]
                first = z3.And(p, z3.Not(L.any_of([z3.And(q, self._same([w[k] for k in keys], key))
                                                    for q, w in slots[:i]])))
                members = [z3.And(q, self._same([w[k] for k in keys], key)) for q, w in slots]
                groups.append((first, key, members))
        else:
            groups.append((L.true(), [], [q for q, _w in slots]))   # one tuple, even over nothing
        out = []
        for present, key, members in groups:
            values = []
            for a, i in aggs:
                if i is None or (a.func == "COUNT" and slides):
                    counted = members
                else:
                    counted = [z3.And(m, z3.Not(L.is_null(w[i]))) for m, (_q, w) in zip(members, slots)]
                n = z3.Sum([z3.If(c, z3.RealVal(1, L.ctx), z3.RealVal(0, L.ctx)) for c in counted]) \
                    if counted else z3.RealVal(0, L.ctx)
                if a.func == "COUNT":
                    values.append(L.Val.num(n))
                    continue
                some = L.any_of(counted)
                if a.func in ("SUM", "AVG"):
                    total = z3.Sum([z3.If(c, L.Val.n(w[i]), z3.RealVal(0, L.ctx)) for c, (_q, w) in zip(counted, slots)]) \
                        if counted else z3.RealVal(0, L.ctx)
                    empty = L.constant(0) if slides and a.func == "SUM" else L.NULL
                    value = total if a.func == "SUM" else total / n
                    values.append(z3.If(some, L.Val.num(value), empty))
                    continue
                best = L.NULL
                for c, (_q, w) in zip(counted, slots):
                    x = w[i]
                    nums = z3.And(L.is_num(x), L.is_num(best))
                    strs = z3.And(L.is_str(x), L.is_str(best))
                    if a.func == "MAX":
                        wins = z3.Or(z3.And(nums, L.Val.n(x) > L.Val.n(best)), z3.And(strs, L.Val.s(x) > L.Val.s(best)))
                    else:
                        wins = z3.Or(z3.And(nums, L.Val.n(x) < L.Val.n(best)), z3.And(strs, L.Val.s(x) < L.Val.s(best)))
                    best = z3.If(z3.And(c, z3.Or(L.is_null(best), wins)), x, best)
                values.append(best)
            out.append((present, key + values))
        return self._out(attrs, out)

    def product(self, e: ast.Binary, outer: Optional[str] = None):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        self._check_no_clash(left, right, e)
        attrs = left.attrs + right.attrs
        L = self.L
        sym = {"left": "⟕", "right": "⟖", "full": "⟗"}.get(outer, "⋈")
        where = f"the inputs of {sym}"
        cond = e.condition
        if cond is not None:
            self._check_condition(cond, attrs, where)

        def holds(row):
            return self.condition(cond, attrs, row, where)[0] if cond is not None else L.true()
        ls, rs = self._slots(left), self._slots(right)
        if len(ls) * len(rs) > MAX_SLOTS:
            raise Unsupported("too many tuple slots")
        out = [(z3.And(p, q, holds(v + w)), v + w) for p, v in ls for q, w in rs]
        nulls_r = [L.NULL] * len(right.attrs)
        nulls_l = [L.NULL] * len(left.attrs)
        if outer in ("left", "full"):
            out += [(z3.And(p, z3.Not(L.any_of([z3.And(q, holds(v + w)) for q, w in rs]))), v + nulls_r) for p, v in ls]
        if outer in ("right", "full"):
            out += [(z3.And(q, z3.Not(L.any_of([z3.And(p, holds(v + w)) for p, v in ls]))), nulls_l + w) for q, w in rs]
        return self._out(attrs, out)

    def natural_join(self, e: ast.Binary, outer: Optional[str]):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        pairs, rkeep, attrs = self._natural_join_plan(left, right, e)
        L = self.L
        ls, rs = self._slots(left), self._slots(right)
        if len(ls) * len(rs) > MAX_SLOTS:
            raise Unsupported("too many tuple slots")

        def match(v, w):
            return L.all_of([z3.And(v[i] == w[j], z3.Not(L.is_null(v[i]))) for i, j in pairs])
        out = [(z3.And(p, q, match(v, w)), v + [w[j] for j in rkeep]) for p, v in ls for q, w in rs]
        if outer in ("left", "full"):
            out += [(z3.And(p, z3.Not(L.any_of([z3.And(q, match(v, w)) for q, w in rs]))), v + [L.NULL] * len(rkeep))
                    for p, v in ls]
        if outer in ("right", "full"):
            for q, w in rs:
                row = [L.NULL] * len(left.attrs)
                for i, j in pairs:
                    row[i] = w[j]
                out.append((z3.And(q, z3.Not(L.any_of([z3.And(p, match(v, w)) for p, v in ls]))),
                            row + [w[j] for j in rkeep]))
        return self._out(attrs, out)

    def set_op(self, e: ast.Binary):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        order = self._set_op_order(left, right, e)
        ls = self._distinct(self._slots(left))
        rs = [(q, [w[i] for i in order]) for q, w in self._slots(right)]
        if e.op == "union":
            return self._out(left.attrs, self._distinct(ls + rs))
        if e.op == "intersect":
            return self._out(left.attrs, [(z3.And(p, self._contains(rs, v)), v) for p, v in ls])
        return self._out(left.attrs, [(z3.And(p, z3.Not(self._contains(rs, v))), v) for p, v in ls])

    def division(self, e: ast.Binary):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        if e.op != "division":
            raise Unsupported(e.op)
        lidx = {a.name.casefold(): i for i, a in enumerate(left.attrs)}
        ridx = {a.name.casefold(): i for i, a in enumerate(right.attrs)}
        missing = [k for k in ridx if k not in lidx]
        keep = [i for k, i in lidx.items() if k not in ridx]
        if len(lidx) != len(left.attrs) or len(ridx) != len(right.attrs) or missing or not keep:
            return Evaluator.division(self, e)          # raises the evaluator's error
        bcols = [lidx[k] for k in ridx]
        rorder = list(ridx.values())
        ls, rs = self._slots(left), self._slots(right)
        L = self.L
        out = []
        for p, v in ls:
            a = [v[i] for i in keep]
            covered = [z3.Implies(q, L.any_of([z3.And(p2, self._same([v2[i] for i in keep], a),
                                                      self._same([v2[i] for i in bcols], [w[j] for j in rorder]))
                                               for p2, v2 in ls]))
                       for q, w in rs]
            out.append((z3.And(p, L.all_of(covered)), a))
        return self._out([left.attrs[i] for i in keep], self._distinct(out))


def _differ(L: Logic, a: List[Slot], b: List[Slot], bag: bool) -> z3.BoolRef:
    def same(v, w):
        return L.all_of([x == y for x, y in zip(v, w)])
    if not bag:
        missing = [z3.And(p, z3.Not(L.any_of([z3.And(q, same(w, v)) for q, w in b]))) for p, v in a]
        extra = [z3.And(q, z3.Not(L.any_of([z3.And(p, same(v, w)) for p, v in a]))) for q, w in b]
        return L.any_of(missing + extra)

    def count(slots, v):
        return z3.Sum([z3.If(z3.And(p, same(w, v)), z3.IntVal(1, L.ctx), z3.IntVal(0, L.ctx)) for p, w in slots]) \
            if slots else z3.IntVal(0, L.ctx)
    return L.any_of([z3.And(p, count(a, v) != count(b, v)) for p, v in a + b])


def search(a: ast.Program, b: ast.Program, schema: Database, options: EvalOptions, bag: bool,
           k: int, units: int, seconds: float):
    """Tuples (table → rows) with at most k per table on which a and b may differ, the
    solver's work, or (None, work). The caller checks the tuples for real."""
    L = Logic(schema)
    try:
        enc = _Bounded(L, options, k)
        ra = enc.run(a)
        rb = enc.run(b)
    except (Unsupported, RAError, z3.Z3Exception):
        return None, 0
    ka, kb = column_keys(ra.columns), column_keys(rb.columns)
    if sorted(ka) != sorted(kb) or len(set(ka)) != len(ka):
        return None, 0
    order = [kb.index(x) for x in ka]
    b_slots = [(q, [w[i] for i in order]) for q, w in rb.rows]
    s = z3.Solver(ctx=L.ctx)
    s.set("rlimit", max(units, 1))
    s.set("timeout", max(int(seconds * 1000), 1))
    try:
        s.add(*enc.constraints())
        s.add(_differ(L, ra.rows, b_slots, bag))
        result = s.check()
    except z3.Z3Exception:
        return None, 0
    work = _units(s)
    if result != z3.sat:
        return None, work
    m = s.model()
    from app.core.ra.equivalence import _python, _NOT_A_VALUE   # noqa: E402 (shared value reader)
    rows: Dict[str, List[tuple]] = {}
    for key, slots in enc.base.items():
        t = L.used[key]
        found = []
        for p, v in slots:
            if z3.is_true(m.eval(p, model_completion=True)):
                vals = tuple(_python(L, m.eval(x, model_completion=True)) for x in v)
                if any(x is _NOT_A_VALUE for x in vals):
                    return None, work
                found.append(vals)
        rows[t.name] = found
    return rows, work


def _units(s: z3.Solver) -> int:
    try:
        return int(s.statistics().get_key_value("rlimit count"))
    except z3.Z3Exception:
        return 0
