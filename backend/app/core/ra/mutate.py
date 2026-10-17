"""Deliberately wrong versions ("mutants") of a model answer, for the grader's self-test.

Each mutant changes the model answer in exactly one place, in the way students commonly
go wrong (the slides' list of common mistakes):

  comparison      <  ↔ ≤,  > ↔ ≥,  < ↔ >,  = ↔ ≠,  a numeric constant ± 1
  condition       AND ↔ OR, one side of an AND dropped, NOT dropped, a whole σ dropped
  aggregate       MIN ↔ MAX, SUM ↔ AVG
  "all" vs "any"  R ÷ S replaced by "at least one of S" (a join where ÷ is needed)
  set operators   ∪ ↔ ∩, R − S → S − R, R − S → R ∩ S
  joins           outer join → inner join, inner → left outer, θ-join condition dropped (×)

When a question is created, the grader generates test databases until every mutant
gives a different result from the model answer on at least one of them ("the mutant is
killed"). A test set that kills every likely mistake is strong evidence it will also
catch a student who makes one. A mutant that is never killed is either a real gap in
the test data or *equivalent* to the model answer (e.g. < vs ≤ on a key that can never
be equal); either way it is shown to staff.
"""
from dataclasses import dataclass, replace
from typing import Iterator, List, Optional, Tuple

from app.core.ra import ast

MAX_MUTANTS = 300

_OP_SWAPS = {"<": ["<=", ">"], "<=": ["<", ">="], ">": [">=", "<"], ">=": [">", "<="],
             "=": ["<>"], "<>": ["="]}
_SHOW = {"<>": "≠", "<=": "≤", ">=": "≥"}


def _show(op: str) -> str:
    return _SHOW.get(op, op)


@dataclass
class Mutant:
    description: str
    line: Optional[int]
    program: ast.Program


Variant = Tuple[str, Optional[int], object]   # (description, line, new node)


def mutants(program: ast.Program) -> List[Mutant]:
    out: List[Mutant] = []
    for k, stmt in enumerate(program.statements):
        for desc, line, new_expr in _expr_variants(stmt.expr):
            statements = list(program.statements)
            statements[k] = replace(stmt, expr=new_expr)
            where = line or stmt.pos.line
            out.append(Mutant(f"line {where}: {desc}" if where else desc, where, ast.Program(statements)))
            if len(out) >= MAX_MUTANTS:
                return out
    return out


# ── relational expressions ───────────────────────────────────────────────────
def _expr_variants(e) -> Iterator[Variant]:
    if isinstance(e, ast.Relation):
        return
    line = e.pos.line
    if isinstance(e, ast.Select):
        yield f"σ {e.condition} removed", line, e.child
        for desc, cline, cond in _cond_variants(e.condition):
            yield desc, cline or line, replace(e, condition=cond)
        for v in _expr_variants(e.child):
            yield v[0], v[1], replace(e, child=v[2])
        return
    if isinstance(e, ast.Group):
        for i, agg in enumerate(e.aggregates):
            for new in {"MIN": ["MAX"], "MAX": ["MIN"], "SUM": ["AVG"], "AVG": ["SUM"]}.get(agg.func, []):
                aggs = list(e.aggregates)
                aggs[i] = replace(agg, func=new)
                yield f"{agg.func} changed to {new}", agg.pos.line or line, replace(e, aggregates=aggs)
        for v in _expr_variants(e.child):
            yield v[0], v[1], replace(e, child=v[2])
        return
    if isinstance(e, (ast.Project, ast.Rename, ast.Distinct)):
        for v in _expr_variants(e.child):
            yield v[0], v[1], replace(e, child=v[2])
        return
    yield from _binary_variants(e)
    for v in _expr_variants(e.left):
        yield v[0], v[1], replace(e, left=v[2])
    for v in _expr_variants(e.right):
        yield v[0], v[1], replace(e, right=v[2])


def _binary_variants(e: ast.Binary) -> Iterator[Variant]:
    line = e.pos.line
    if e.op == "division":
        yield "÷ replaced by “at least one” (any instead of all)", line, replace(e, op="division_any")
    elif e.op == "union":
        yield "∪ changed to ∩", line, replace(e, op="intersect")
    elif e.op == "intersect":
        yield "∩ changed to ∪", line, replace(e, op="union")
    elif e.op == "difference":
        yield "the two sides of − swapped", line, replace(e, left=e.right, right=e.left)
        yield "− changed to ∩", line, replace(e, op="intersect")
    elif e.op in ("left_join", "right_join", "full_join"):
        inner = "theta_join" if e.condition is not None else "natural_join"
        yield "outer join changed to an inner join", line, replace(e, op=inner)
    elif e.op == "natural_join":
        yield "⋈ changed to a left outer join ⟕", line, replace(e, op="left_join")
    elif e.op == "theta_join":
        yield f"join condition {e.condition} dropped (⋈ became ×)", line, replace(e, op="product", condition=None)
    if e.condition is not None:
        for desc, cline, cond in _cond_variants(e.condition):
            yield desc, cline or line, replace(e, condition=cond)


# ── conditions ───────────────────────────────────────────────────────────────
def _cond_variants(c) -> Iterator[Variant]:
    if isinstance(c, ast.Comparison):
        line = c.pos.line
        for op in _OP_SWAPS.get(c.op, []):
            yield f"{_show(c.op)} changed to {_show(op)} in {c}", line, replace(c, op=op)
        for side in ("left", "right"):
            lit = getattr(c, side)
            if isinstance(lit, ast.Literal) and isinstance(lit.value, (int, float)) \
                    and not isinstance(lit.value, bool):
                for delta in (-1, 1):
                    new = replace(lit, value=lit.value + delta)
                    yield f"constant {lit} changed to {new} in {c}", line, replace(c, **{side: new})
        return
    if isinstance(c, ast.Not):
        yield f"NOT removed from {c}", None, c.operand
        for v in _cond_variants(c.operand):
            yield v[0], v[1], ast.Not(v[2])
        return
    other = "OR" if c.op == "AND" else "AND"
    yield f"{c.op} changed to {other} in {c}", None, replace(c, op=other)
    if c.op == "AND":
        yield f"condition {c.right} dropped", None, c.left
        yield f"condition {c.left} dropped", None, c.right
    for v in _cond_variants(c.left):
        yield v[0], v[1], replace(c, left=v[2])
    for v in _cond_variants(c.right):
        yield v[0], v[1], replace(c, right=v[2])
