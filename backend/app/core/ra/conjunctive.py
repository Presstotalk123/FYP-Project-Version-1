"""Exact equivalence for answers built only from σ (with =), Π, ⋈, ×, ρ and ∪.

Such answers are *unions of conjunctive queries* (UCQs). For them, unlike for answers
using −, ÷ or γ, equivalence can be decided exactly, on every possible database, with
no test data (Chandra & Merlin 1977; Sagiv & Yannakakis 1980 for unions):

  1. Translate answer A into its conjunctive queries. Each one is a *pattern*: the base
     tuples it needs (atoms) and the output tuple built from them. Freeze each pattern
     into a tiny database — its *canonical database* — by giving every variable its own
     made-up value.
  2. Run answer B on each canonical database of A. If B produces A's frozen output tuple
     on every one of them, then every tuple A can ever return, B returns too: A ⊆ B
     on **all** databases.
  3. Equivalent ⇔ A ⊆ B and B ⊆ A.

If a canonical database of A makes B miss A's tuple, that database is a counterexample:
the two answers differ on it. Translation reuses the evaluator's own rules for names,
qualifiers and joins (it subclasses ``Evaluator``), so "conjunctive" means exactly what
the evaluator computes. The result holds for set comparison only (Π keeps duplicates in
bag comparison), and anything outside the fragment raises ``NotConjunctive``, after
which the grader falls back to testing on generated databases.
"""
from dataclasses import dataclass
from itertools import count
from typing import Dict, List, Optional, Sequence, Tuple

from app.core.ra import ast
from app.core.ra.compare import align, column_keys, norm_row
from app.core.ra.evaluator import Evaluator, EvalOptions, Rel, evaluate
from app.core.ra.schema import Database

MAX_BRANCHES = 64


class NotConjunctive(Exception):
    """The answer uses something outside σ(=), Π, ⋈, ×, ρ, ∪, ∩, δ."""


@dataclass(frozen=True)
class Var:
    id: int


@dataclass(frozen=True)
class Const:
    value: object


Term = object  # Var | Const


@dataclass(frozen=True)
class Branch:
    """One conjunctive query: output terms, the base tuples it needs, equalities between terms."""
    terms: Tuple[Term, ...]
    atoms: Tuple[Tuple[str, Tuple[Term, ...]], ...]
    eqs: Tuple[Tuple[Term, Term], ...] = ()


def _join(a: Branch, b: Branch, eqs=()) -> Branch:
    return Branch(a.terms + b.terms, a.atoms + b.atoms, a.eqs + b.eqs + tuple(eqs))


class _Symbolic(Evaluator):
    """The evaluator, but each "row" is a Branch (a pattern) instead of a tuple of values."""

    def __init__(self, db: Database):
        super().__init__(db, trace=False)
        self._ids = count()

    def _fresh(self) -> Var:
        return Var(next(self._ids))

    def _cap(self, branches: List[Branch]) -> List[Branch]:
        if len(branches) > MAX_BRANCHES:
            raise NotConjunctive("too many alternatives")
        return branches

    def eval(self, e):
        if isinstance(e, (ast.Group,)):
            raise NotConjunctive("γ")
        if isinstance(e, ast.Binary) and e.op not in ("product", "theta_join", "natural_join", "union", "intersect"):
            raise NotConjunctive(e.op)
        if isinstance(e, ast.Binary) and e.op == "intersect":
            return self.intersect(e)
        return super().eval(e)

    # relations: each occurrence gets fresh variables
    def relation(self, e: ast.Relation):
        key = e.name.casefold()
        if key in self.assigned:
            name, rel = self.assigned[key]
            return Rel(rel.attrs, [self._rename_apart(b) for b in rel.rows]), {}
        rel, _ = super().relation(e)
        table = self.db.lookup(e.name)
        terms = tuple(self._fresh() for _ in rel.attrs)
        return Rel(rel.attrs, [Branch(terms, ((table.name, terms),))]), {}

    def _rename_apart(self, b: Branch) -> Branch:
        mapping: Dict[Var, Var] = {}

        def m(t):
            if isinstance(t, Var):
                if t not in mapping:
                    mapping[t] = self._fresh()
                return mapping[t]
            return t
        return Branch(tuple(m(t) for t in b.terms),
                      tuple((n, tuple(m(t) for t in ts)) for n, ts in b.atoms),
                      tuple((m(x), m(y)) for x, y in b.eqs))

    # conditions become equalities; OR becomes alternatives; anything else is not conjunctive
    def _alternatives(self, c, rel: Rel, where: str) -> List[List[Tuple[object, object]]]:
        """Each alternative is a list of (term-getter, term-getter) equalities."""
        if isinstance(c, ast.BoolOp):
            left = self._alternatives(c.left, rel, where)
            right = self._alternatives(c.right, rel, where)
            if c.op == "OR":
                return left + right
            return [a + b for a in left for b in right]
        if isinstance(c, ast.Not) or c.op != "=":
            raise NotConjunctive("only = conditions")
        return [[(self._getter(c.left, rel, where), self._getter(c.right, rel, where))]]

    def _getter(self, v, rel: Rel, where: str):
        if isinstance(v, ast.AttrRef):
            i = self.resolve(v, rel.attrs, where)
            return lambda b, i=i: b.terms[i]
        if isinstance(v, ast.Literal):
            return lambda b, x=v.value: Const(x)
        raise NotConjunctive("arithmetic")

    def _filter(self, rel: Rel, cond, where: str) -> List[Branch]:
        alts = self._alternatives(cond, rel, where)
        return self._cap([Branch(b.terms, b.atoms, b.eqs + tuple((f(b), g(b)) for f, g in alt))
                          for b in rel.rows for alt in alts])

    def select(self, e: ast.Select):
        child, _ = self.eval(e.child)
        return Rel(child.attrs, self._filter(child, e.condition, "the input of σ")), {}

    def project(self, e: ast.Project):
        child, _ = self.eval(e.child)
        indexes, _fns, attrs = self._project_plan(e, child)
        if any(i is None for i in indexes):
            raise NotConjunctive("arithmetic in Π")
        return Rel(attrs, [Branch(tuple(b.terms[i] for i in indexes), b.atoms, b.eqs) for b in child.rows]), {}

    def product(self, e: ast.Binary, outer: Optional[str] = None):
        if outer:
            raise NotConjunctive("outer join")
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        self._check_no_clash(left, right, e)
        rel = Rel(left.attrs + right.attrs, self._cap([_join(a, b) for a in left.rows for b in right.rows]))
        if e.condition is not None:
            rel = Rel(rel.attrs, self._filter(rel, e.condition, "the inputs of ⋈"))
        return rel, {}

    def natural_join(self, e: ast.Binary, outer: Optional[str]):
        if outer:
            raise NotConjunctive("outer join")
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        pairs, rkeep, attrs = self._natural_join_plan(left, right, e)
        rows = []
        for a in left.rows:
            for b in right.rows:
                eqs = [(a.terms[i], b.terms[j]) for i, j in pairs]
                rows.append(Branch(a.terms + tuple(b.terms[j] for j in rkeep), a.atoms + b.atoms,
                                   a.eqs + b.eqs + tuple(eqs)))
        return Rel(attrs, self._cap(rows)), {}

    def set_op(self, e: ast.Binary):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        order = self._set_op_order(left, right, e)
        moved = [Branch(tuple(b.terms[i] for i in order), b.atoms, b.eqs) for b in right.rows]
        return Rel(left.attrs, self._cap(list(left.rows) + moved)), {}

    def intersect(self, e: ast.Binary):
        left, _ = self.eval(e.left)
        right, _ = self.eval(e.right)
        order = self._set_op_order(left, right, e)
        rows = [Branch(a.terms, a.atoms + b.atoms,
                       a.eqs + b.eqs + tuple((a.terms[k], b.terms[i]) for k, i in enumerate(order)))
                for a in left.rows for b in right.rows]
        return Rel(left.attrs, self._cap(rows)), {}


def to_ucq(program: ast.Program, db: Database) -> Tuple[List[str], List[Branch]]:
    """The answer's output columns and its conjunctive queries. Raises NotConjunctive."""
    sym = _Symbolic(db)
    result = sym.run(program)
    return result.columns, list(result.rows)


# ── canonical databases ──────────────────────────────────────────────────────
def _solve(b: Branch) -> Optional[Dict[Term, object]]:
    """Give every term a value respecting the equalities; None if they contradict (x = 1 and x = 2)."""
    parent: Dict[Term, Term] = {}

    def find(t):
        parent.setdefault(t, t)
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    terms = set(b.terms) | {t for _, ts in b.atoms for t in ts} | {t for eq in b.eqs for t in eq}
    for t in terms:
        find(t)
    for x, y in b.eqs:
        parent[find(x)] = find(y)
    value: Dict[Term, object] = {}
    for t in terms:
        if isinstance(t, Const):
            root = find(t)
            if root in value and norm_row((value[root],)) != norm_row((t.value,)):
                return None
            value[root] = t.value
    fresh = count(1)
    for t in terms:
        root = find(t)
        if root not in value:
            # A made-up value no constant in any answer can equal.
            value[root] = f"⟨v{next(fresh)}⟩"
    return {t: value[find(t)] for t in terms}


def canonical_database(b: Branch, db: Database) -> Optional[Tuple[Database, tuple]]:
    """The smallest database the pattern needs, and the output tuple it then produces."""
    assignment = _solve(b)
    if assignment is None:
        return None
    rows: Dict[str, List[tuple]] = {}
    for name, ts in b.atoms:
        rows.setdefault(name, []).append(tuple(assignment[t] for t in ts))
    rows = {k: list(dict.fromkeys(v)) for k, v in rows.items()}
    return db.with_rows(rows), tuple(assignment[t] for t in b.terms)


@dataclass
class ContainmentResult:
    contained: bool
    counterexample: Optional[Database] = None   # where A has a tuple B lacks


def contained_in(a_columns: Sequence[str], a_branches: Sequence[Branch],
                 b_program: ast.Program, db: Database, options: EvalOptions = EvalOptions()) -> ContainmentResult:
    """Is every tuple of A (given as conjunctive queries) also a tuple of B, on every database?"""
    for branch in a_branches:
        canon = canonical_database(branch, db)
        if canon is None:
            continue                                   # a contradictory pattern returns nothing
        cdb, head = canon
        result = evaluate(b_program, cdb, trace=False, options=options)
        if column_keys(result.columns) != column_keys(a_columns) and \
                sorted(column_keys(result.columns)) != sorted(column_keys(a_columns)):
            return ContainmentResult(False, cdb)
        got = {norm_row(r) for r in align(result.rows, result.columns, a_columns)}
        if norm_row(head) not in got:
            return ContainmentResult(False, cdb)
    return ContainmentResult(True)


@dataclass
class ProofResult:
    equivalent: bool
    counterexample: Optional[Database] = None


def prove(a: ast.Program, b: ast.Program, db: Database, options: EvalOptions = EvalOptions()) -> ProofResult:
    """Decide exactly whether two answers are equivalent. Raises NotConjunctive if either
    is outside the fragment (the caller then tests on generated databases instead)."""
    a_cols, a_branches = to_ucq(a, db)
    b_cols, b_branches = to_ucq(b, db)
    forward = contained_in(a_cols, a_branches, b, db, options)
    if not forward.contained:
        return ProofResult(False, forward.counterexample)
    backward = contained_in(b_cols, b_branches, a, db, options)
    if not backward.contained:
        return ProofResult(False, backward.counterexample)
    return ProofResult(True)
