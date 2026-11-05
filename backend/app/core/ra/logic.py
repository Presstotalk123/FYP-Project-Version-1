"""Turn an RA answer into logic, so the Z3 solver can reason about *every* database.

Each relation an answer computes becomes a formula ``member(t)`` that is true exactly
when the tuple ``t`` is in the result, for whatever the stored tables hold. The stored
tables are uninterpreted predicates (``Course(c1, c2)`` is "this tuple is in Course"),
so a formula speaks about all databases at once. equivalence.py then asks Z3 whether
some valid database has a tuple in one answer and not in the other.

Values are one Z3 type with three kinds, as in the evaluator: NULL, a number (an exact
real; an INTEGER column only holds whole numbers) and a string. Every operator follows
evaluator.py exactly, including its corner cases:

  * conditions use three-valued logic: each condition becomes a pair (definitely true,
    definitely false), NOT swaps them, and σ / θ-joins keep the "definitely true" part;
    values of different kinds are never equal and never ordered;
  * natural joins never match a NULL; ∪, ∩, −, ÷ and δ treat NULL like a value;
  * outer joins pad with NULL; a right natural join keeps the right-hand join values;
  * Π a, b(R) = { (a, b) | some tuple of R has them }: an ∃ over R's other attributes;
  * − is "and not", ÷ is "∃ some tuple, and for every tuple of the divisor …";
  * γ MIN/MAX is written in logic ("a value in the group, and none bigger"), with the
    evaluator's NULL rules and the one tuple γ gives over an empty relation;
  * γ COUNT/SUM/AVG can't be written in first-order logic. Each becomes an unknown
    function of the group, which the prover shares between the two answers only when
    their inputs are proved to be the same relation (equivalence.py, ``AggregateClasses``).

The translation reuses the evaluator for every name rule (it subclasses ``Evaluator``,
like the evaluator's own checks: qualifiers, ambiguity, ρ, union compatibility), so an
answer means the same here as when it runs. Each relation also records whether it can
contain duplicates (``dup_free``), which matters for bag comparison and COUNT.

Anything this can't express raises ``Unsupported``; the grader then relies on testing.
"""
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import count
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import z3

from app.core.ra import ast
from app.core.ra import errors as E
from app.core.ra.errors import RAError
from app.core.ra.evaluator import Attr, Evaluator, EvalOptions, Rel, make_labels
from app.core.ra.schema import Database, Table

MAX_NODES = 400            # bigger answers are left to testing


class Unsupported(Exception):
    """The answer uses something the logic translation doesn't cover."""


class Logic:
    """The shared vocabulary of one proof: the value type, one predicate per stored
    table, the constraints of the schema, and fresh variable names. One Z3 context per
    proof, so proofs in different threads never share solver state."""

    def __init__(self, schema: Database):
        self.ctx = z3.Context()
        self.schema = schema
        v = z3.Datatype("Val", self.ctx)
        v.declare("null")
        v.declare("num", ("n", z3.RealSort(self.ctx)))
        v.declare("str", ("s", z3.StringSort(self.ctx)))
        self.Val = v.create()
        self.NULL = self.Val.null
        self._ids = count()
        self.tables: Dict[str, z3.FuncDeclRef] = {}
        self.used: Dict[str, Table] = {}

    # ── values ────────────────────────────────────────────────────────────────
    def fresh(self, hint: str = "u") -> z3.ExprRef:
        return z3.Const(f"{hint}{next(self._ids)}", self.Val)

    def fresh_list(self, n: int, hint: str = "u") -> List[z3.ExprRef]:
        return [self.fresh(hint) for _ in range(n)]

    def true(self) -> z3.BoolRef:
        return z3.BoolVal(True, self.ctx)

    def false(self) -> z3.BoolRef:
        return z3.BoolVal(False, self.ctx)

    def all_of(self, items: Sequence[z3.BoolRef]) -> z3.BoolRef:
        items = [i for i in items if not z3.is_true(i)]
        if any(z3.is_false(i) for i in items):
            return self.false()
        return self.true() if not items else items[0] if len(items) == 1 else z3.And(*items)

    def any_of(self, items: Sequence[z3.BoolRef]) -> z3.BoolRef:
        items = [i for i in items if not z3.is_false(i)]
        if any(z3.is_true(i) for i in items):
            return self.true()
        return self.false() if not items else items[0] if len(items) == 1 else z3.Or(*items)

    def exists(self, variables: Sequence[z3.ExprRef], body: z3.BoolRef) -> z3.BoolRef:
        return z3.Exists(list(variables), body) if variables else body

    def constant(self, value) -> z3.ExprRef:
        if value is None:
            return self.NULL
        if isinstance(value, bool):
            raise Unsupported("a true/false value")
        if isinstance(value, (int, float)):
            exact = Fraction(repr(value)) if isinstance(value, float) else Fraction(value)
            return self.Val.num(z3.RealVal(str(exact), self.ctx))
        if isinstance(value, str):
            return self.Val.str(z3.StringVal(value, self.ctx))
        raise Unsupported(f"a {type(value).__name__} value")

    def is_null(self, v) -> z3.BoolRef:
        return self.Val.is_null(v)

    def is_num(self, v) -> z3.BoolRef:
        return self.Val.is_num(v)

    def is_str(self, v) -> z3.BoolRef:
        return self.Val.is_str(v)

    # ── stored tables and the schema's constraints ────────────────────────────
    def table(self, t: Table) -> z3.FuncDeclRef:
        key = t.name.casefold()
        if key not in self.tables:
            sorts = [self.Val] * len(t.columns) + [z3.BoolSort(self.ctx)]
            self.tables[key] = z3.Function(f"T_{t.name}", *sorts)
            self.used[key] = t
        return self.tables[key]

    def _domain(self, t: Table, col: str, affinity: str, v) -> z3.BoolRef:
        if affinity == "INTEGER":
            kind = z3.And(self.is_num(v), z3.IsInt(self.Val.n(v)))
        elif affinity == "REAL":
            kind = self.is_num(v)
        elif affinity == "TEXT":
            kind = self.is_str(v)
        else:                                   # NUMERIC: numbers, or text such as dates
            kind = z3.Not(self.is_null(v))
        return kind                             # stored tables hold no NULLs (see axioms)

    def axioms(self) -> List[z3.BoolRef]:
        """What every valid database satisfies: each attribute holds a value of its type
        and never NULL (as in the relational model and the course: NULLs only come from
        outer joins), each primary key is unique, and each foreign key points at an
        existing tuple. Tables reached through foreign keys are included, since a
        constraint can matter through a chain (Enrolled → Course → Dept)."""
        pending = list(self.used.values())
        seen = set(self.used)
        while pending:
            t = pending.pop()
            for fk in t.foreign_keys:
                parent = self.schema.lookup(fk.ref_table)
                if parent is not None and parent.name.casefold() not in seen:
                    seen.add(parent.name.casefold())
                    self.table(parent)
                    pending.append(parent)
        out = []
        for key, t in list(self.used.items()):
            pred = self.tables[key]
            cols = t.column_names
            x = self.fresh_list(len(cols), "x")
            out.append(z3.ForAll(x, z3.Implies(pred(*x), self.all_of(
                [self._domain(t, c, aff, xi) for (c, aff), xi in zip(t.columns, x)]))))
            if t.primary_key and len(t.primary_key) < len(cols):
                y = self.fresh_list(len(cols), "y")
                k = [cols.index(c) for c in t.primary_key]
                out.append(z3.ForAll(x + y, z3.Implies(
                    z3.And(pred(*x), pred(*y), *[x[i] == y[i] for i in k]),
                    self.all_of([x[i] == y[i] for i in range(len(cols)) if i not in k]))))
            for fk in t.foreign_keys:
                parent = self.schema.lookup(fk.ref_table)
                if parent is None:
                    continue
                pcols = parent.column_names
                if any(c not in cols for c in fk.columns) or any(c not in pcols for c in fk.ref_columns):
                    continue
                z = self.fresh_list(len(pcols), "z")
                ppred = self.table(parent)
                link = [z[pcols.index(rc)] == x[cols.index(c)] for c, rc in zip(fk.columns, fk.ref_columns)]
                out.append(z3.ForAll(x, z3.Implies(pred(*x), z3.Exists(z, z3.And(ppred(*z), *link)))))
        return out


@dataclass(eq=False)
class Sym:
    """A relation as logic: ``member(t)`` builds the formula "t is in it" for a list of
    value terms. ``override`` lets the prover swap a sub-relation for a shared unknown
    one once it has proved two of them equal (equivalence.py)."""
    build: Callable[[List[z3.ExprRef]], z3.BoolRef]
    arity: int
    dup_free: bool
    text: str                         # a canonical description, equal for identical sub-answers
    size: int                         # operators in it
    override: Optional[Callable[[List[z3.ExprRef]], z3.BoolRef]] = None

    def member(self, t: Sequence[z3.ExprRef]) -> z3.BoolRef:
        if len(t) != self.arity:
            raise Unsupported("arity")
        return (self.override or self.build)(list(t))


@dataclass(eq=False)
class AggregateUse:
    """A γ COUNT/SUM/AVG in an answer: the prover gives it a function (shared with an
    equal one in the other answer) before any formula uses it."""
    func: str
    attr_label: Optional[str]         # the aggregated attribute's label in the input; None = *
    key_labels: List[str]             # the grouping attributes' labels, in group-by order
    input: Sym
    input_labels: List[str]
    function: Optional[z3.FuncDeclRef] = None


@dataclass
class Encoded:
    columns: List[str]                # the answer's final labels
    result: Sym
    nodes: List[Tuple[List[str], Sym]] = field(default_factory=list)    # every sub-relation, inner first
    aggregates: List[AggregateUse] = field(default_factory=list)


class _Translate(Evaluator):
    """The evaluator, but every relation is a Sym instead of a list of tuples."""

    def __init__(self, logic: Logic, options: EvalOptions):
        super().__init__(logic.schema, trace=False, options=options)
        self.L = logic
        self.nodes: List[Tuple[List[str], Sym]] = []
        self.aggregates: List[AggregateUse] = []

    def _rel(self, attrs: List[Attr], sym: Sym) -> Tuple[Rel, dict]:
        if sym.size > MAX_NODES:
            raise Unsupported("too big")
        rel = Rel(attrs, sym)                      # rows hold the Sym
        self.nodes.append((make_labels(attrs), sym))
        return rel, {}

    @staticmethod
    def _sym(rel: Rel) -> Sym:
        return rel.rows                            # type: ignore[return-value]

    def eval(self, e):
        if isinstance(e, ast.Distinct):
            child, _ = self.eval(e.child)
            c = self._sym(child)
            return self._rel(child.attrs, Sym(c.member, c.arity, True, f"δ({c.text})", c.size + 1))
        if isinstance(e, ast.Binary) and e.op not in (
                "product", "theta_join", "natural_join", "left_join", "right_join", "full_join",
                "union", "intersect", "difference", "division"):
            raise Unsupported(e.op)
        return super().eval(e)

    # ── values and conditions ────────────────────────────────────────────────
    def term(self, v, attrs: Sequence[Attr], row: List[z3.ExprRef], where: str) -> z3.ExprRef:
        L = self.L
        if isinstance(v, ast.AttrRef):
            return row[self.resolve(v, attrs, where)]
        if isinstance(v, ast.Literal):
            return L.constant(v.value)
        a = self.term(v.left, attrs, row, where)
        b = self.term(v.right, attrs, row, where)
        both = z3.And(L.is_num(a), L.is_num(b))
        x, y = L.Val.n(a), L.Val.n(b)
        if v.op == "+":
            val = x + y
        elif v.op == "-":
            val = x - y
        elif v.op == "*":
            val = x * y
        elif v.op == "/":
            both = z3.And(both, y != 0)
            val = x / y
        else:
            raise Unsupported(f"arithmetic {v.op}")
        return z3.If(both, L.Val.num(val), L.NULL)

    def _compare(self, a, op: str, b) -> Tuple[z3.BoolRef, z3.BoolRef]:
        L = self.L
        known = z3.And(z3.Not(L.is_null(a)), z3.Not(L.is_null(b)))
        nums = z3.And(L.is_num(a), L.is_num(b))
        strs = z3.And(L.is_str(a), L.is_str(b))
        x, y, s, t = L.Val.n(a), L.Val.n(b), L.Val.s(a), L.Val.s(b)
        ops = {"=": (x == y, s == t), "<>": (x != y, s != t), "<": (x < y, s < t),
               "<=": (x <= y, s <= t), ">": (x > y, s > t), ">=": (x >= y, s >= t)}
        if op not in ops:
            raise Unsupported(f"comparison {op}")
        on_nums, on_strs = ops[op]
        holds = z3.If(nums, on_nums, z3.If(strs, on_strs, z3.BoolVal(op == "<>", L.ctx)))
        return z3.And(known, holds), z3.And(known, z3.Not(holds))

    def condition(self, c, attrs: Sequence[Attr], row: List[z3.ExprRef], where: str) -> Tuple[z3.BoolRef, z3.BoolRef]:
        """(definitely true, definitely false) — three-valued logic, as in the evaluator."""
        if isinstance(c, ast.BoolOp):
            lt, lf = self.condition(c.left, attrs, row, where)
            rt, rf = self.condition(c.right, attrs, row, where)
            if c.op == "AND":
                return z3.And(lt, rt), z3.Or(lf, rf)
            return z3.Or(lt, rt), z3.And(lf, rf)
        if isinstance(c, ast.Not):
            t, f = self.condition(c.operand, attrs, row, where)
            return f, t
        return self._compare(self.term(c.left, attrs, row, where), c.op, self.term(c.right, attrs, row, where))

    def _check_condition(self, c, attrs: Sequence[Attr], where: str) -> None:
        """Resolve every name now, so errors appear in the same place as in the evaluator."""
        self.condition(c, attrs, self.L.fresh_list(len(attrs)), where)

    # ── relations ─────────────────────────────────────────────────────────────
    def relation(self, e: ast.Relation):
        key = e.name.casefold()
        if key in self.assigned:
            _name, rel = self.assigned[key]
            return rel, {}
        table = self.db.lookup(e.name)
        if table is None:
            return super().relation(e)                 # raises the evaluator's error
        pred = self.L.table(table)
        attrs = [Attr(c, frozenset({table.name}), t) for c, t in table.columns]
        sym = Sym(lambda t, p=pred: p(*t), len(attrs), bool(table.primary_key), table.name.casefold(), 1)
        return self._rel(attrs, sym)

    def rename(self, e: ast.Rename):
        rel, _ = super().rename(e)
        c = self._sym(rel)
        names = ",".join(a.name for a in rel.attrs)
        return self._rel(rel.attrs, Sym(c.member, c.arity, c.dup_free, f"ρ[{e.relation}({names})]({c.text})",
                                        c.size + 1))

    def select(self, e: ast.Select):
        child, _ = self.eval(e.child)
        c = self._sym(child)
        where = "the input of σ"
        self._check_condition(e.condition, child.attrs, where)
        attrs = child.attrs

        def build(t):
            return z3.And(c.member(t), self.condition(e.condition, attrs, t, where)[0])
        return self._rel(attrs, Sym(build, c.arity, c.dup_free, f"σ[{e.condition}]({c.text})", c.size + 1))

    def project(self, e: ast.Project):
        child, _ = self.eval(e.child)
        c = self._sym(child)
        indexes, _fns, attrs = self._project_plan(e, child)
        where = "the input of Π"
        cattrs = child.attrs
        for item in e.items:
            if not isinstance(item.value, ast.AttrRef):
                self.term(item.value, cattrs, self.L.fresh_list(len(cattrs)), where)
        copies_all = all(i in indexes for i in range(len(cattrs)))

        def build(t):
            u: List[Optional[z3.ExprRef]] = [None] * len(cattrs)
            eqs = []
            for k, i in enumerate(indexes):
                if i is not None:
                    if u[i] is None:
                        u[i] = t[k]
                    else:
                        eqs.append(t[k] == u[i])
            free = []
            for i in range(len(u)):
                if u[i] is None:
                    u[i] = self.L.fresh()
                    free.append(u[i])
            for k, (i, item) in enumerate(zip(indexes, e.items)):
                if i is None:
                    eqs.append(t[k] == self.term(item.value, cattrs, u, where))
            return self.L.exists(free, self.L.all_of([c.member(u)] + eqs))
        text = f"Π[{', '.join(str(i) for i in e.items)}]({c.text})"
        return self._rel(attrs, Sym(build, len(attrs), c.dup_free and copies_all, text, c.size + 1))

    def group_plan(self, e: ast.Group, child: Rel) -> Tuple[List[int], List[Tuple[ast.Aggregate, Optional[int]]], List[Attr]]:
        """The grouping attributes' indexes, each aggregate with its attribute's index
        (None for COUNT(*)), and the output attributes, with the evaluator's checks."""
        where = "the input of γ"
        keys = [self.resolve(g, child.attrs, where) for g in e.group_by]
        aggs: List[Tuple[ast.Aggregate, Optional[int]]] = []
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
        attrs = [child.attrs[i] for i in keys] + [
            Attr(a.alias, frozenset(), "INTEGER" if a.func == "COUNT" else "NUMERIC") for a, _ in aggs]
        out_labels = make_labels(attrs)
        dup = next((lbl for lbl in out_labels if [x.casefold() for x in out_labels].count(lbl.casefold()) > 1), None)
        if dup:
            raise RAError(E.DUPLICATE_ATTRIBUTE, f"“{dup}” appears twice in γ.", e.pos.line, e.pos.col)
        return keys, aggs, attrs

    def group(self, e: ast.Group):
        child, _ = self.eval(e.child)
        c = self._sym(child)
        L = self.L
        keys, aggs, attrs = self.group_plan(e, child)
        labels = child.labels
        slides = self.options.aggregate_nulls == "slides"
        uses: List[Optional[AggregateUse]] = []
        for a, i in aggs:
            if a.func in ("MIN", "MAX"):
                uses.append(None)
                continue
            # COUNT(attr) in "slides" mode counts every tuple, the same as COUNT(*).
            label = None if i is None or (a.func == "COUNT" and slides) else labels[i]
            use = AggregateUse(a.func, label, [labels[k] for k in keys], c, labels)
            self.aggregates.append(use)
            uses.append(use)
        nk = len(keys)

        def in_group(g: List[z3.ExprRef], extra=None):
            """∃ a tuple of the input in group g (and, optionally, meeting extra(u))."""
            u: List[Optional[z3.ExprRef]] = [None] * c.arity
            eqs = []
            for gk, k in zip(g, keys):
                if u[k] is None:
                    u[k] = gk
                else:
                    eqs.append(u[k] == gk)
            free = []
            for i in range(c.arity):
                if u[i] is None:
                    u[i] = L.fresh()
                    free.append(u[i])
            body = [c.member(u)] + eqs + ([extra(u)] if extra else [])
            return L.exists(free, L.all_of(body))

        def better(x, y, func):
            nums = z3.And(L.is_num(x), L.is_num(y))
            strs = z3.And(L.is_str(x), L.is_str(y))
            if func == "MAX":
                return z3.Or(z3.And(nums, L.Val.n(x) > L.Val.n(y)), z3.And(strs, L.Val.s(x) > L.Val.s(y)))
            return z3.Or(z3.And(nums, L.Val.n(x) < L.Val.n(y)), z3.And(strs, L.Val.s(x) < L.Val.s(y)))

        def build(t):
            g, vals = t[:nk], t[nk:]
            parts = [in_group(g)] if nk else []
            for (a, i), use, v in zip(aggs, uses, vals):
                if use is None:                        # MIN / MAX
                    some = in_group(g, lambda u, i=i: z3.Not(L.is_null(u[i])))
                    hit = in_group(g, lambda u, i=i, v=v: u[i] == v)
                    beaten = in_group(g, lambda u, i=i, v=v, f=a.func: z3.And(z3.Not(L.is_null(u[i])), better(u[i], v, f)))
                    parts.append(z3.If(some, z3.And(z3.Not(L.is_null(v)), hit, z3.Not(beaten)), v == L.NULL))
                    continue
                if use.function is None:
                    raise Unsupported("aggregate not prepared")
                order = sorted(range(nk), key=lambda k: use.key_labels[k].casefold())
                value = use.function(*[g[k] for k in order])
                if nk:
                    parts.append(v == value)
                else:
                    empty = {"COUNT": L.constant(0), "SUM": L.constant(0) if slides else L.NULL, "AVG": L.NULL}[a.func]
                    parts.append(z3.If(in_group([]), v == value, v == empty))
            return L.all_of(parts)
        text = f"γ[{', '.join([str(x) for x in e.group_by] + [str(a) for a in e.aggregates])}]({c.text})"
        return self._rel(attrs, Sym(build, len(attrs), True, text, c.size + 1))

    def product(self, e: ast.Binary, outer: Optional[str] = None):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        self._check_no_clash(left, right, e)
        lsym, rsym = self._sym(left), self._sym(right)
        attrs = left.attrs + right.attrs
        nl, nr = lsym.arity, rsym.arity
        L = self.L
        sym = {"left": "⟕", "right": "⟖", "full": "⟗"}.get(outer, "⋈")
        where = f"the inputs of {sym}"
        cond = e.condition
        if cond is not None:
            self._check_condition(cond, attrs, where)

        def holds(row):
            return self.condition(cond, attrs, row, where)[0] if cond is not None else L.true()

        def build(t):
            lt, rt = t[:nl], t[nl:]
            matched = L.all_of([lsym.member(lt), rsym.member(rt), holds(t)])
            options = [matched]
            if outer in ("left", "full"):
                r = L.fresh_list(nr)
                options.append(L.all_of([lsym.member(lt)] + [x == L.NULL for x in rt] +
                                        [z3.Not(L.exists(r, z3.And(rsym.member(r), holds(lt + r))))]))
            if outer in ("right", "full"):
                lv = L.fresh_list(nl)
                options.append(L.all_of([rsym.member(rt)] + [x == L.NULL for x in lt] +
                                        [z3.Not(L.exists(lv, z3.And(lsym.member(lv), holds(lv + rt))))]))
            return L.any_of(options)
        op = {"left": "⟕", "right": "⟖", "full": "⟗"}.get(outer, "×" if cond is None else "⋈")
        text = f"{op}[{cond if cond is not None else ''}]({lsym.text},{rsym.text})"
        return self._rel(attrs, Sym(build, nl + nr, lsym.dup_free and rsym.dup_free and not outer, text,
                                    lsym.size + rsym.size + 1))

    def natural_join(self, e: ast.Binary, outer: Optional[str]):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        pairs, rkeep, attrs = self._natural_join_plan(left, right, e)
        lsym, rsym = self._sym(left), self._sym(right)
        nl, nr = lsym.arity, rsym.arity
        L = self.L

        def right_row(lt, kept):
            r: List[Optional[z3.ExprRef]] = [None] * nr
            for i, j in pairs:
                r[j] = lt[i]
            for k, j in enumerate(rkeep):
                r[j] = kept[k]
            return r

        def keys_known(lt):
            return [z3.Not(L.is_null(lt[i])) for i, _ in pairs]

        def build(t):
            lt, kept = t[:nl], t[nl:]
            options = [L.all_of([lsym.member(lt), rsym.member(right_row(lt, kept))] + keys_known(lt))]
            if outer in ("left", "full"):
                free = L.fresh_list(len(rkeep))
                hit = L.exists(free, L.all_of([rsym.member(right_row(lt, free))]))
                options.append(L.all_of([lsym.member(lt)] + [x == L.NULL for x in kept] +
                                        [z3.Or(z3.Not(L.all_of(keys_known(lt))), z3.Not(hit))]))
            if outer in ("right", "full"):
                # An unmatched right tuple: NULL everywhere on the left except the join
                # attributes, which take the right-hand values.
                key_pos = {i for i, _ in pairs}
                r = right_row(lt, kept)
                others = [lt[i] == L.NULL for i in range(nl) if i not in key_pos]
                lv = L.fresh_list(nl)
                matched = L.exists(lv, L.all_of([lsym.member(lv)] + [lv[i] == lt[i] for i, _ in pairs]))
                options.append(L.all_of([rsym.member(r)] + others +
                                        [z3.Or(z3.Not(L.all_of(keys_known(lt))), z3.Not(matched))]))
            return L.any_of(options)
        op = {"left": "⟕", "right": "⟖", "full": "⟗"}.get(outer, "⋈")
        return self._rel(attrs, Sym(build, len(attrs), lsym.dup_free and rsym.dup_free and not outer,
                                    f"{op}({lsym.text},{rsym.text})", lsym.size + rsym.size + 1))

    def set_op(self, e: ast.Binary):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        order = self._set_op_order(left, right, e)
        lsym, rsym = self._sym(left), self._sym(right)
        L = self.L

        def aligned(t):
            r: List[Optional[z3.ExprRef]] = [None] * len(order)
            for k, i in enumerate(order):
                r[i] = t[k]
            return r

        def build(t):
            a, b = lsym.member(t), rsym.member(aligned(t))
            if e.op == "union":
                return z3.Or(a, b)
            if e.op == "intersect":
                return z3.And(a, b)
            return z3.And(a, z3.Not(b))
        symbol = {"union": "∪", "intersect": "∩", "difference": "−"}[e.op]
        return self._rel(left.attrs, Sym(build, lsym.arity, True, f"{symbol}({lsym.text},{rsym.text})",
                                         lsym.size + rsym.size + 1))

    def division(self, e: ast.Binary):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        if e.op != "division":
            raise Unsupported(e.op)
        lidx = {a.name.casefold(): i for i, a in enumerate(left.attrs)}
        ridx = {a.name.casefold(): i for i, a in enumerate(right.attrs)}
        if len(lidx) != len(left.attrs) or len(ridx) != len(right.attrs):
            raise RAError(E.INVALID_DIVISION, "÷ needs distinct attribute names on both sides.", e.pos.line, e.pos.col)
        missing = [right.attrs[i].name for k, i in ridx.items() if k not in lidx]
        keep = [i for k, i in lidx.items() if k not in ridx]
        if missing or not keep:
            return super().division(e)                 # raises the evaluator's error
        bcols = [lidx[k] for k in ridx]
        rorder = list(ridx.values())
        lsym, rsym = self._sym(left), self._sym(right)
        L = self.L

        def left_row(a, b):
            row: List[Optional[z3.ExprRef]] = [None] * lsym.arity
            for k, i in enumerate(keep):
                row[i] = a[k]
            for m, i in enumerate(bcols):
                row[i] = b[m]
            return row

        def build(t):
            b1 = L.fresh_list(len(bcols))
            b2 = L.fresh_list(len(bcols))
            r: List[Optional[z3.ExprRef]] = [None] * rsym.arity
            for m, i in enumerate(rorder):
                r[i] = b2[m]
            return z3.And(L.exists(b1, lsym.member(left_row(t, b1))),
                          z3.ForAll(b2, z3.Implies(rsym.member(r), lsym.member(left_row(t, b2)))))
        return self._rel([left.attrs[i] for i in keep], Sym(build, len(keep), True,
                                                            f"÷({lsym.text},{rsym.text})", lsym.size + rsym.size + 1))


def encode(program: ast.Program, logic: Logic, options: EvalOptions = EvalOptions()) -> Encoded:
    """The answer as logic. Raises Unsupported, or RAError for an answer that doesn't run."""
    tr = _Translate(logic, options)
    result = tr.run(program)
    return Encoded(list(result.columns), result.rows, tr.nodes, tr.aggregates)   # type: ignore[arg-type]
