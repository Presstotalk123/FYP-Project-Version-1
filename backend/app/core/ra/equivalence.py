"""Prove two RA answers equivalent on every valid database, or find one where they differ.

A *valid* database is one the schema allows: every attribute holds a value of its type,
primary keys are unique and every foreign key points at an existing tuple. Stored tables
hold no NULLs, as in the relational model and the course (NULLs only appear after outer
joins, whose NULL rules are still followed exactly), and as in the test databases.

How a proof goes (logic.py turns each answer into a formula):

  1. **Aggregates.** γ COUNT/SUM/AVG can't be written in logic, so each one is an
     unknown function of its group. Two of them (in either answer) share one function
     only if their inputs are the same relation: written identically, or proved equal
     here (as sets, and both free of duplicates, so the counts agree too).
  2. **The whole answer.** Ask Z3 for a valid database and a tuple that is in one answer
     but not the other. *Unsatisfiable* means no such database exists: the answers are
     equivalent on every valid database. A *model* is a candidate counterexample.
  3. **Piece by piece.** If Z3 can't decide within its share of the work, prove pairs of
     corresponding parts equal (the same attributes; biggest first), replace each proved
     pair by one shared unknown relation, and try the whole again. This is what lets a
     deeply nested answer (− inside −, γ over −) be proved when it has the model
     answer's overall shape, without the solver ever seeing the full nesting at once.
  4. **Counterexample search.** Quantified formulas are hard for a solver to *satisfy*,
     so if no proof was found, bounded.py searches every database with at most 1, 2,
     then 3 tuples per table, without quantifiers, for one where the answers differ.
  5. Otherwise: **unknown**. The grader then relies on its test databases.

Two safeguards keep this trustworthy:

  * A counterexample is never taken on the solver's word: it is read out of the model,
    loaded into SQLite with the schema's constraints switched on, and both answers are
    run on it with the real evaluator. Only if they really differ is it used.
  * The work is limited by Z3's deterministic resource counter (``rlimit``), not a clock,
    so the same answer gets the same result on any server, however busy. A wall-clock
    cap well above the budget only guards against a stuck solver.

Equivalence of relational algebra is undecidable in general (it contains first-order
logic), so no method decides every pair; "unknown" is the honest answer for the rest.
"""
import sqlite3
import time
from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Dict, List, Optional, Sequence, Tuple

import z3

from app.core.ra import ast, bounded
from app.core.ra.compare import column_keys, equal, same_columns
from app.core.ra.errors import RAError
from app.core.ra.evaluator import EvalOptions, evaluate
from app.core.ra.generator import _parents_first, _validator, collect_hints
from app.core.ra.logic import AggregateUse, Encoded, Logic, Sym, Unsupported, encode
from app.core.ra.schema import Database

# Z3's resource units; about 2 seconds of solving for a typical answer on the server.
BUDGET = 5_000_000
PROOF_SHARE = 0.7              # steps 1–3; the rest is kept for the counterexample search
MAIN_SHARE = 0.4               # the first attempt at the whole answer
PART_SHARE = 0.05              # each part (or aggregate input) proved on its own
MAX_PARTS = 6
SEARCH_SIZES = (1, 2, 3)       # tuples per table in the counterexample search (bounded.py)
WALL_SECONDS = 8.0             # safety net only; the budget above normally stops first
MAX_CANDIDATE_TUPLES = 20_000  # reading a counterexample out of a model
MAX_ROWS_PER_TABLE = 40


@dataclass
class Proof:
    status: str                              # equivalent | different | unknown
    counterexample: Optional[Database] = None
    how: str = ""                            # whole | by_parts | (unknown:) the reason
    work: int = 0                            # resource units used

    @property
    def equivalent(self) -> bool:
        return self.status == "equivalent"


def stored(db: Database) -> Optional[Database]:
    """The tuples as a valid database stores them, or None if the schema forbids them.

    SQLite checks the types' affinity (3.0 in an INTEGER column becomes 3), primary keys,
    UNIQUE, CHECK and foreign keys. NULLs are refused here: stored tables hold none."""
    if any(v is None for t in db.tables for r in t.rows for v in r):
        return None
    conn = _validator(db)
    try:
        conn.execute("BEGIN")
        conn.execute("PRAGMA defer_foreign_keys = ON")
        for t in _parents_first(db.tables):
            if t.rows:
                marks = ", ".join("?" for _ in t.columns)
                conn.executemany(f'INSERT INTO "{t.name}" VALUES ({marks})', t.rows)
        rows = {t.name: [tuple(r) for r in conn.execute(f'SELECT * FROM "{t.name}"')] for t in db.tables}
        conn.execute("COMMIT")
        return db.with_rows(rows)
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def valid(db: Database) -> bool:
    return stored(db) is not None


def differ(a: ast.Program, b: ast.Program, db: Database, options: EvalOptions, bag: bool) -> bool:
    try:
        ra = evaluate(a, db, trace=False, options=options)
        rb = evaluate(b, db, trace=False, options=options)
    except RAError:
        return False
    return not equal(ra.columns, ra.rows, rb.columns, rb.rows, bag=bag)


class _Session:
    def __init__(self, logic: Logic, a_prog: ast.Program, b_prog: ast.Program, options: EvalOptions, bag: bool):
        self.L = logic
        self.a_prog, self.b_prog = a_prog, b_prog
        self.options, self.bag = options, bag
        self.work = 0
        self.started = time.monotonic()
        self.extra_axioms: List[z3.BoolRef] = []
        self._n_functions = 0
        self._count = 0

    # ── one solver call ───────────────────────────────────────────────────────
    def check(self, a: Sym, b: Sym, perm: Sequence[int], units: int):
        """Is there a valid database where a and b (b's columns in ``perm`` order) differ?
        Returns (z3 result, model or None)."""
        L = self.L
        units = min(units, int(BUDGET * PROOF_SHARE) - self.work)
        left = WALL_SECONDS - (time.monotonic() - self.started)
        if units <= 0 or left <= 0:
            return z3.unknown, None
        t = L.fresh_list(a.arity, "t")
        tb: List[Optional[z3.ExprRef]] = [None] * a.arity
        for k, i in enumerate(perm):
            tb[i] = t[k]
        try:
            in_a, in_b = a.member(t), b.member(tb)
        except Unsupported:
            return z3.unknown, None
        s = z3.Solver(ctx=L.ctx)
        s.set("rlimit", units)
        s.set("timeout", int(left * 1000))
        s.add(*L.axioms(), *self.extra_axioms)
        s.add(z3.Or(z3.And(in_a, z3.Not(in_b)), z3.And(in_b, z3.Not(in_a))))
        result = s.check()
        # Z3 counts work per context, across solvers: charge this call what it added.
        count = _units(s)
        self.work += max(count - self._count, 0)
        self._count = max(count, self._count)
        return result, (s.model() if result == z3.sat else None)

    # ── step 1: aggregates ────────────────────────────────────────────────────
    def prepare_aggregates(self, uses: Sequence[AggregateUse]) -> None:
        L = self.L
        reps: List[AggregateUse] = []
        for use in uses:                                  # inner γ first (encoding order)
            for rep in reps:
                if self._same_aggregate(use, rep):
                    use.function = rep.function
                    break
            else:
                self._n_functions += 1
                use.function = z3.Function(f"agg{self._n_functions}", *([L.Val] * len(use.key_labels)), L.Val)
                g = L.fresh_list(len(use.key_labels), "g")
                v = use.function(*g)
                if use.func == "COUNT":
                    fact = z3.And(L.is_num(v), z3.IsInt(L.Val.n(v)), L.Val.n(v) >= 0)
                else:
                    fact = z3.Or(L.is_null(v), L.is_num(v))
                self.extra_axioms.append(z3.ForAll(g, fact) if g else fact)
                reps.append(use)

    def _same_aggregate(self, u: AggregateUse, r: AggregateUse) -> bool:
        fold = lambda xs: sorted(x.casefold() for x in xs)   # noqa: E731
        if u.func != r.func or fold(u.input_labels) != fold(r.input_labels) \
                or fold(u.key_labels) != fold(r.key_labels) \
                or (u.attr_label or "").casefold() != (r.attr_label or "").casefold():
            return False
        if len(set(fold(u.input_labels))) != len(u.input_labels):
            return False
        if u.input.text == r.input.text and column_keys(u.input_labels) == column_keys(r.input_labels):
            return True
        if not (u.input.dup_free and r.input.dup_free):
            return False                                   # equal sets, but the counts could differ
        perm = _perm(r.input_labels, u.input_labels)
        result, _ = self.check(r.input, u.input, perm, int(BUDGET * PART_SHARE))
        return result == z3.unsat

    # ── step 3: piece by piece ────────────────────────────────────────────────
    def abstract_parts(self, a: Encoded, b: Encoded) -> int:
        """Replace pairs of parts proved equal by a shared unknown relation; how many."""
        pairs = []
        for la, sa in a.nodes:
            if sa is a.result or sa.size < 2:
                continue
            for lb, sb in b.nodes:
                if sb is b.result or sb.size < 2 or sa.arity != sb.arity:
                    continue
                if not same_columns(la, lb) or len({x.casefold() for x in la}) != len(la):
                    continue
                pairs.append((sa.size + sb.size, la, sa, lb, sb))
        pairs.sort(key=lambda p: -p[0])
        done, tried, used, inside = 0, 0, set(), []
        for _size, la, sa, lb, sb in pairs:
            if id(sa) in used or id(sb) in used:
                continue
            if any(sa.text in ta and sb.text in tb for ta, tb in inside):
                continue                                  # already inside a replaced pair
            perm = _perm(la, lb)
            if sa.text != sb.text:
                if tried >= MAX_PARTS:
                    continue
                tried += 1
                result, _ = self.check(sa, sb, perm, int(BUDGET * PART_SHARE))
                if result != z3.unsat:
                    continue
            shared = z3.Function(f"part{done}", *([self.L.Val] * sa.arity), z3.BoolSort(self.L.ctx))
            sa.override = lambda t, f=shared: f(*t)
            sb.override = lambda t, f=shared, p=perm: f(*[t[i] for i in p])
            used.update({id(sa), id(sb)})
            inside.append((sa.text, sb.text))
            done += 1
        return done

    # ── reading a counterexample out of a model ───────────────────────────────
    def counterexample(self, model: z3.ModelRef) -> Optional[Database]:
        L = self.L
        values: Dict[str, z3.ExprRef] = {}

        def add(v):
            if v is not None and v.sort() == L.Val and _python(L, v) is not _NOT_A_VALUE:
                values.setdefault(v.sexpr(), v)
        def walk(e, seen):
            """Every value the model mentions, also inside its "else" expressions."""
            if not isinstance(e, z3.ExprRef) or e.get_id() in seen or len(seen) > 5000:
                return
            seen.add(e.get_id())
            add(e)
            if z3.is_app(e):
                for k in range(e.num_args()):
                    walk(e.arg(k), seen)
            elif z3.is_quantifier(e):
                walk(e.body(), seen)
        seen: set = set()
        for d in model.decls():
            interp = model[d]
            if isinstance(interp, z3.FuncInterp):
                for entry in interp.as_list()[:-1]:
                    for x in entry:
                        walk(x, seen)
                walk(interp.else_value(), seen)
            else:
                walk(interp, seen)
        hints = collect_hints([self.a_prog, self.b_prog])
        for consts in hints.constants.values():
            for _op, c in consts:
                add(_safe_constant(L, c))
        for _op, c in hints.loose_constants:
            add(_safe_constant(L, c))
        add(L.NULL)
        add(L.constant(0))
        add(L.constant(1))
        candidates = list(values.values())
        rows: Dict[str, List[tuple]] = {}
        for key, t in L.used.items():
            pred = L.tables[key]
            per_column = []
            for col, aff in t.columns:
                ok = [v for v in candidates if _fits(L, v, aff, col in t.not_null)]
                per_column.append(ok)
            total = 1
            for ok in per_column:
                total *= max(len(ok), 1)
            if total > MAX_CANDIDATE_TUPLES:
                return None
            found = []
            for tup in product(*per_column):
                if z3.is_true(model.eval(pred(*tup), model_completion=True)):
                    found.append(tuple(_python(L, v) for v in tup))
                    if len(found) > MAX_ROWS_PER_TABLE:
                        return None
            rows[t.name] = found
        db = stored(L.schema.with_rows(rows))
        if db is None or not differ(self.a_prog, self.b_prog, db, self.options, self.bag):
            return None
        return db


_NOT_A_VALUE = object()


def _python(L: Logic, v: z3.ExprRef):
    if not z3.is_app(v):
        return _NOT_A_VALUE
    if v.decl().eq(L.NULL.decl()):
        return None
    if v.decl().eq(L.Val.num) and v.num_args() == 1:
        n = v.arg(0)
        if z3.is_rational_value(n):
            f = Fraction(n.numerator_as_long(), n.denominator_as_long())
            return int(f) if f.denominator == 1 else float(f)
        return _NOT_A_VALUE
    if v.decl().eq(L.Val.str) and v.num_args() == 1:
        s = v.arg(0)
        return s.as_string() if z3.is_string_value(s) else _NOT_A_VALUE
    return _NOT_A_VALUE


def _safe_constant(L: Logic, c):
    try:
        return L.constant(c)
    except Unsupported:
        return None


def _fits(L: Logic, v: z3.ExprRef, affinity: str, not_null: bool) -> bool:
    p = _python(L, v)
    if p is None:
        return not not_null
    if affinity == "INTEGER":
        return isinstance(p, int)
    if affinity == "REAL":
        return isinstance(p, (int, float))
    if affinity == "TEXT":
        return isinstance(p, str)
    return True


def _units(s: z3.Solver) -> int:
    try:
        return int(s.statistics().get_key_value("rlimit count"))
    except z3.Z3Exception:
        return 0


def _perm(a_labels: Sequence[str], b_labels: Sequence[str]) -> List[int]:
    """For each column of a, the index of the same-named column of b."""
    bk = column_keys(b_labels)
    return [bk.index(k) for k in column_keys(a_labels)]


def prove(a: ast.Program, b: ast.Program, schema: Database, options: EvalOptions = EvalOptions(),
          bag: bool = False) -> Proof:
    """Are answers a and b equivalent on every valid database of ``schema``?"""
    try:
        logic = Logic(schema)
        ea, eb = encode(a, logic, options), encode(b, logic, options)
    except Unsupported as e:
        return Proof("unknown", how=f"not expressible ({e})")
    except RAError as e:
        return Proof("unknown", how=f"error ({e.message})")
    if not same_columns(ea.columns, eb.columns) or len(set(column_keys(ea.columns))) != len(ea.columns):
        return Proof("unknown", how="different attributes")
    session = _Session(logic, a, b, options, bag)
    # In bag comparison equal sets are only enough when neither answer can repeat a tuple.
    sets_suffice = not bag or (ea.result.dup_free and eb.result.dup_free)
    try:
        session.prepare_aggregates(ea.aggregates + eb.aggregates)
        perm = _perm(ea.columns, eb.columns)
        result, model = session.check(ea.result, eb.result, perm, int(BUDGET * MAIN_SHARE))
        how = "whole"
        if result == z3.unknown and session.abstract_parts(ea, eb):
            result, model = session.check(ea.result, eb.result, perm, BUDGET)
            how = "by_parts"
    except z3.Z3Exception as e:
        return Proof("unknown", how=f"solver error ({e})", work=session.work)
    if result == z3.unsat and sets_suffice:
        return Proof("equivalent", how=how, work=session.work)
    if result == z3.sat and model is not None:
        db = session.counterexample(model)
        if db is not None:
            return Proof("different", db, how=how, work=session.work)
    db = _search(a, b, schema, options, bag, session)
    if db is not None:
        return Proof("different", db, how="search", work=session.work)
    if result == z3.unsat:
        return Proof("unknown", how="duplicates could differ", work=session.work)
    return Proof("unknown", how="undecided within the budget", work=session.work)


def _search(a, b, schema: Database, options: EvalOptions, bag: bool, session: _Session) -> Optional[Database]:
    """Step 4: every database with at most k tuples per table, k = 1, 2, 3."""
    allowance = BUDGET - int(BUDGET * PROOF_SHARE)
    used = 0
    for k in SEARCH_SIZES:
        seconds = WALL_SECONDS - (time.monotonic() - session.started)
        if allowance - used <= 0 or seconds <= 0:
            break
        rows, work = bounded.search(a, b, schema, options, bag, k, allowance - used, seconds)
        used += work
        session.work += work
        if rows is None:
            continue
        db = stored(schema.with_rows(rows))
        if db is not None and differ(a, b, db, options, bag):
            return db
    return None
