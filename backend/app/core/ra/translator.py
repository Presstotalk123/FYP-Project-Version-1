"""Translate a parsed RA program into one SQLite query.

Checking and SQL generation happen in a single bottom-up pass: each node needs its
children's output schema both to validate attribute references and to name the SQL
columns it selects, so a separate checker would recompute the same information.

Design decisions (FYP Design Document 02, §4.3):
  * Set semantics — every operator's output is duplicate-free (DISTINCT / UNION).
  * Each node becomes a sub-query with a fresh alias (t0, t1, …) whose output columns
    are named by the node's attribute names: the bare name when it is unique in the
    result, otherwise ``Qualifier.name``. Names are deterministic because the grader
    hashes column names.
  * Natural join keeps each common attribute once; the merged attribute can be
    referred to through either input's relation name.
"""
import difflib
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Sequence, Tuple

from app.core.ra import ast
from app.core.ra import errors as E
from app.core.ra.errors import RAError
from app.core.ra.schema import Schema

_SET_SQL = {"union": "UNION", "intersect": "INTERSECT", "difference": "EXCEPT"}
_SYMBOL = {"product": "×", "natural_join": "⋈", "theta_join": "⋈", "union": "∪",
           "intersect": "∩", "difference": "−", "division": "÷"}


@dataclass(frozen=True)
class Attr:
    name: str
    quals: FrozenSet[str]      # relation names this attribute can be qualified with
    type: str

    def qualified(self) -> str:
        return f"{sorted(self.quals)[0]}.{self.name}" if self.quals else self.name


@dataclass
class Rel:
    """A compiled sub-expression: its SQL, output attributes and their column labels."""
    sql: str
    attrs: List[Attr]
    labels: List[str]
    tree: dict


@dataclass
class TranslationResult:
    sql: str
    tree: dict
    output_attributes: List[str]
    operators_used: List[str]
    warnings: List[RAError] = field(default_factory=list)


def q(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def make_labels(attrs: Sequence[Attr]) -> List[str]:
    labels = []
    for a in attrs:
        same = [b for b in attrs if b.name.casefold() == a.name.casefold()]
        if len(same) == 1:
            labels.append(a.name)
            continue
        others = set().union(*(b.quals for b in same if b is not a))
        own = sorted(a.quals - others) or sorted(a.quals)
        labels.append(f"{own[0]}.{a.name}")
    return labels


class _Translator:
    def __init__(self, schema: Schema):
        self.schema = schema
        self.alias_no = 0
        self.assigned: Dict[str, Tuple[str, Rel]] = {}
        self.operators: List[str] = []
        self.warnings: List[RAError] = []

    # ── helpers ───────────────────────────────────────────────────────────────
    def alias(self) -> str:
        a = f"t{self.alias_no}"
        self.alias_no += 1
        return a

    def used(self, op: str) -> None:
        if op not in self.operators:
            self.operators.append(op)

    @staticmethod
    def env(rel: Rel, alias: str) -> List[Tuple[Attr, str]]:
        return [(a, f"{alias}.{q(lbl)}") for a, lbl in zip(rel.attrs, rel.labels)]

    def resolve(self, ref: ast.AttrRef, env: List[Tuple[Attr, str]], where: str) -> Tuple[Attr, str]:
        name = ref.name.casefold()
        matches = [(a, sql) for a, sql in env if a.name.casefold() == name]
        if ref.qualifier:
            qual = ref.qualifier.casefold()
            in_scope = {qq.casefold() for a, _ in env for qq in a.quals}
            if qual not in in_scope:
                scope = ", ".join(sorted({qq for a, _ in env for qq in a.quals}))
                raise RAError(E.UNKNOWN_RELATION,
                              f"“{ref.qualifier}” is not a relation available {where}.",
                              ref.pos.line, ref.pos.col, f"Relations in scope: {scope}.")
            matches = [(a, sql) for a, sql in matches if qual in {qq.casefold() for qq in a.quals}]
        if not matches:
            available = ", ".join(make_labels([a for a, _ in env]))
            close = difflib.get_close_matches(ref.name, [a.name for a, _ in env], n=1)
            hint = f"Did you mean “{close[0]}”?" if close else None
            raise RAError(E.UNKNOWN_ATTRIBUTE,
                          f"Attribute “{ref}” is not in {where} ({available}).",
                          ref.pos.line, ref.pos.col, hint)
        if len(matches) > 1:
            options = " or ".join(a.qualified() for a, _ in matches)
            raise RAError(E.AMBIGUOUS_ATTRIBUTE, f"“{ref}” is ambiguous {where}: use {options}.",
                          ref.pos.line, ref.pos.col)
        return matches[0]

    def condition(self, cond, env, where: str) -> str:
        if isinstance(cond, ast.BoolOp):
            return f"({self.condition(cond.left, env, where)} {cond.op} {self.condition(cond.right, env, where)})"
        if isinstance(cond, ast.Not):
            return f"(NOT {self.condition(cond.operand, env, where)})"
        sides = []
        types = []
        for side in (cond.left, cond.right):
            if isinstance(side, ast.AttrRef):
                attr, sql = self.resolve(side, env, where)
                sides.append(sql)
                types.append(attr.type)
            elif isinstance(side.value, str):
                sides.append("'" + side.value.replace("'", "''") + "'")
                types.append("STRING")
            else:
                sides.append(repr(side.value))
                types.append("NUMBER")
        if {"TEXT", "NUMBER"} <= set(types) or ("STRING" in types and {"INTEGER", "REAL"} & set(types)):
            self.warnings.append(RAError(E.TYPE_MISMATCH,
                                         f"“{cond}” compares text with a number — is that intended?",
                                         cond.pos.line, cond.pos.col))
        return f"{sides[0]} {cond.op} {sides[1]}"

    @staticmethod
    def select_list(env: List[Tuple[Attr, str]], labels: List[str]) -> str:
        return ", ".join(f"{sql} AS {q(lbl)}" for (_, sql), lbl in zip(env, labels))

    @staticmethod
    def node(op: str, label: str, rel_labels: List[str], kids: Sequence[Rel], pos: ast.Pos) -> dict:
        return {"op": op, "label": label, "schema": list(rel_labels),
                "children": [k.tree for k in kids], "line": pos.line, "col": pos.col}

    # ── expressions ───────────────────────────────────────────────────────────
    def compile(self, e) -> Rel:
        if isinstance(e, ast.Relation):
            return self.relation(e)
        if isinstance(e, ast.Select):
            return self.select(e)
        if isinstance(e, ast.Project):
            return self.project(e)
        if isinstance(e, ast.Rename):
            return self.rename(e)
        if e.op in ("product", "theta_join"):
            return self.product(e)
        if e.op == "natural_join":
            return self.natural_join(e)
        if e.op in _SET_SQL:
            return self.set_op(e)
        return self.division(e)

    def relation(self, e: ast.Relation) -> Rel:
        key = e.name.casefold()
        if key in self.assigned:
            name, rel = self.assigned[key]
            attrs = [Attr(a.name, a.quals | {name}, a.type) for a in rel.attrs]
            return Rel(f"SELECT * FROM {q(name)}", attrs, list(rel.labels),
                       self.node("relation", name, rel.labels, [], e.pos))
        found = self.schema.lookup(e.name)
        if not found:
            close = difflib.get_close_matches(e.name, self.schema.table_names, n=1)
            raise RAError(E.UNKNOWN_RELATION,
                          f"Relation “{e.name}” does not exist. Available: {', '.join(self.schema.table_names)}.",
                          e.pos.line, e.pos.col, f"Did you mean “{close[0]}”?" if close else None)
        table, cols = found
        attrs = [Attr(c.name, frozenset({table}), c.type) for c in cols]
        labels = [c.name for c in cols]
        sql = f"SELECT DISTINCT {', '.join(q(c) for c in labels)} FROM {q(table)}"
        return Rel(sql, attrs, labels, self.node("relation", table, labels, [], e.pos))

    def select(self, e: ast.Select) -> Rel:
        self.used("select")
        child = self.compile(e.child)
        a = self.alias()
        cond = self.condition(e.condition, self.env(child, a), "the input of σ")
        sql = f"SELECT * FROM ({child.sql}) AS {a} WHERE {cond}"
        return Rel(sql, child.attrs, child.labels,
                   self.node("select", f"σ[{_cond_text(e.condition)}]", child.labels, [child], e.pos))

    def project(self, e: ast.Project) -> Rel:
        self.used("project")
        child = self.compile(e.child)
        a = self.alias()
        env = self.env(child, a)
        picked: List[Tuple[Attr, str]] = []
        for ref in e.attributes:
            attr, sql = self.resolve(ref, env, "the input of π")
            if any(p is attr for p, _ in picked):
                raise RAError(E.DUPLICATE_ATTRIBUTE, f"“{ref}” is listed twice in π.",
                              ref.pos.line, ref.pos.col)
            picked.append((attr, sql))
        attrs = [p for p, _ in picked]
        labels = make_labels(attrs)
        sql = f"SELECT DISTINCT {self.select_list(picked, labels)} FROM ({child.sql}) AS {a}"
        shown = ", ".join(str(r) for r in e.attributes)
        return Rel(sql, attrs, labels, self.node("project", f"π[{shown}]", labels, [child], e.pos))

    def rename(self, e: ast.Rename) -> Rel:
        self.used("rename")
        child = self.compile(e.child)
        a = self.alias()
        names = e.attributes or [x.name for x in child.attrs]
        if len(names) != len(child.attrs):
            raise RAError(E.RENAME_ARITY,
                          f"ρ lists {len(names)} new attribute names but the relation has "
                          f"{len(child.attrs)} ({', '.join(child.labels)}).", e.pos.line, e.pos.col)
        folded = [n.casefold() for n in names]
        dup = next((n for n in names if folded.count(n.casefold()) > 1), None)
        if dup:
            raise RAError(E.DUPLICATE_ATTRIBUTE,
                          f"After ρ[{e.relation}] the relation would have two attributes called “{dup}”.",
                          e.pos.line, e.pos.col, "List new, distinct attribute names in ρ.")
        attrs = [Attr(n, frozenset({e.relation}), x.type) for n, x in zip(names, child.attrs)]
        labels = make_labels(attrs)
        sql = f"SELECT {self.select_list(self.env(child, a), labels)} FROM ({child.sql}) AS {a}"
        shown = e.relation + (f"({', '.join(e.attributes)})" if e.attributes else "")
        return Rel(sql, attrs, labels, self.node("rename", f"ρ[{shown}]", labels, [child], e.pos))

    def _check_no_clash(self, left: Rel, right: Rel, e: ast.Binary) -> None:
        for la in left.attrs:
            for ra in right.attrs:
                if la.name.casefold() == ra.name.casefold() and la.quals & ra.quals:
                    both = sorted(la.quals & ra.quals)[0]
                    raise RAError(E.SAME_NAME_INPUTS,
                                  f"Both inputs of {_SYMBOL[e.op]} have an attribute {both}.{la.name}, "
                                  "so they could not be told apart.", e.pos.line, e.pos.col,
                                  "Rename one input with ρ first, e.g. ρ[S2](Student).")

    def product(self, e: ast.Binary) -> Rel:
        self.used(e.op)
        left, right = self.compile(e.left), self.compile(e.right)
        self._check_no_clash(left, right, e)
        a, b = self.alias(), self.alias()
        env = self.env(left, a) + self.env(right, b)
        attrs = left.attrs + right.attrs
        labels = make_labels(attrs)
        if e.op == "product":
            join, label = "CROSS JOIN", "×"
            tail = ""
        else:
            cond = self.condition(e.condition, env, "the inputs of ⋈")
            join, label = "JOIN", f"⋈[{_cond_text(e.condition)}]"
            tail = f" ON {cond}"
        sql = (f"SELECT {self.select_list(env, labels)} "
               f"FROM ({left.sql}) AS {a} {join} ({right.sql}) AS {b}{tail}")
        return Rel(sql, attrs, labels, self.node(e.op, label, labels, [left, right], e.pos))

    def natural_join(self, e: ast.Binary) -> Rel:
        self.used("natural_join")
        left, right = self.compile(e.left), self.compile(e.right)
        a, b = self.alias(), self.alias()
        lenv, renv = self.env(left, a), self.env(right, b)
        right_names = {x.name.casefold() for x in right.attrs}
        common = [x.name for x in left.attrs if x.name.casefold() in right_names]
        for name in common:
            for side, rel in (("left", left), ("right", right)):
                if sum(x.name.casefold() == name.casefold() for x in rel.attrs) > 1:
                    raise RAError(E.AMBIGUOUS_ATTRIBUTE,
                                  f"⋈ would join on “{name}”, but the {side} input has more than one "
                                  f"attribute called “{name}”.", e.pos.line, e.pos.col,
                                  "Project or rename first so each input has one.")
        on = []
        attrs: List[Attr] = []
        env: List[Tuple[Attr, str]] = []
        for (la, lsql) in lenv:
            match = next(((ra, rsql) for ra, rsql in renv if ra.name.casefold() == la.name.casefold()), None)
            if match:
                ra, rsql = match
                on.append(f"{lsql} = {rsql}")
                la = Attr(la.name, la.quals | ra.quals, la.type)
            attrs.append(la)
            env.append((la, lsql))
        for (ra, rsql) in renv:
            if ra.name.casefold() not in {c.casefold() for c in common}:
                attrs.append(ra)
                env.append((ra, rsql))
        labels = make_labels(attrs)
        join = f"JOIN ({right.sql}) AS {b} ON {' AND '.join(on)}" if on else f"CROSS JOIN ({right.sql}) AS {b}"
        sql = f"SELECT {self.select_list(env, labels)} FROM ({left.sql}) AS {a} {join}"
        return Rel(sql, attrs, labels, self.node("natural_join", "⋈", labels, [left, right], e.pos))

    def set_op(self, e: ast.Binary) -> Rel:
        self.used(e.op)
        left, right = self.compile(e.left), self.compile(e.right)
        if len(left.attrs) != len(right.attrs):
            raise RAError(E.UNION_INCOMPATIBLE,
                          f"{_SYMBOL[e.op]} needs union-compatible inputs: the left has "
                          f"{len(left.attrs)} attributes ({', '.join(left.labels)}), the right has "
                          f"{len(right.attrs)} ({', '.join(right.labels)}).", e.pos.line, e.pos.col,
                          "Use π on both sides so they have the same attributes.")
        a, b = self.alias(), self.alias()
        sql = f"SELECT * FROM ({left.sql}) AS {a} {_SET_SQL[e.op]} SELECT * FROM ({right.sql}) AS {b}"
        return Rel(sql, left.attrs, left.labels,
                   self.node(e.op, _SYMBOL[e.op], left.labels, [left, right], e.pos))

    def division(self, e: ast.Binary) -> Rel:
        self.used("division")
        left, right = self.compile(e.left), self.compile(e.right)

        def unique_index(rel: Rel, side: str) -> Dict[str, int]:
            idx: Dict[str, int] = {}
            for i, x in enumerate(rel.attrs):
                key = x.name.casefold()
                if key in idx:
                    raise RAError(E.INVALID_DIVISION,
                                  f"÷ needs distinct attribute names, but the {side} input has two "
                                  f"called “{x.name}”.", e.pos.line, e.pos.col)
                idx[key] = i
            return idx

        lidx, ridx = unique_index(left, "left"), unique_index(right, "right")
        missing = [right.attrs[i].name for k, i in ridx.items() if k not in lidx]
        keep = [i for k, i in lidx.items() if k not in ridx]
        if missing or not keep:
            raise RAError(E.INVALID_DIVISION,
                          f"÷ requires the divisor’s attributes ({', '.join(right.labels)}) to be a "
                          f"proper subset of the dividend’s ({', '.join(left.labels)}).",
                          e.pos.line, e.pos.col)
        a, b, c = self.alias(), self.alias(), self.alias()
        attrs = [left.attrs[i] for i in keep]
        labels = make_labels(attrs)
        cols = ", ".join(f"{a}.{q(left.labels[i])} AS {q(lbl)}" for i, lbl in zip(keep, labels))
        match = [f"{c}.{q(left.labels[i])} = {a}.{q(left.labels[i])}" for i in keep]
        match += [f"{c}.{q(left.labels[lidx[k]])} = {b}.{q(right.labels[i])}" for k, i in ridx.items()]
        sql = (f"SELECT DISTINCT {cols} FROM ({left.sql}) AS {a} WHERE NOT EXISTS ("
               f"SELECT 1 FROM ({right.sql}) AS {b} WHERE NOT EXISTS ("
               f"SELECT 1 FROM ({left.sql}) AS {c} WHERE {' AND '.join(match)}))")
        return Rel(sql, attrs, labels, self.node("division", "÷", labels, [left, right], e.pos))

    # ── program ───────────────────────────────────────────────────────────────
    def program(self, p: ast.Program) -> TranslationResult:
        ctes = []
        assignments = []
        for asg in p.assignments:
            key = asg.name.casefold()
            if self.schema.lookup(asg.name) or key in self.assigned:
                raise RAError(E.INVALID_ASSIGNMENT,
                              f"“{asg.name}” is already the name of a relation; choose another name.",
                              asg.pos.line, asg.pos.col)
            self.used("assignment")
            rel = self.compile(asg.expr)
            self.assigned[key] = (asg.name, rel)
            ctes.append(f"{q(asg.name)} AS ({rel.sql})")
            assignments.append({"name": asg.name, "tree": rel.tree})
        result = self.compile(p.result)
        sql = (f"WITH {', '.join(ctes)} " if ctes else "") + result.sql
        tree = dict(result.tree)
        if assignments:
            tree["assignments"] = assignments
        return TranslationResult(sql, tree, result.labels, self.operators, self.warnings)


def _cond_text(cond) -> str:
    text = str(cond)
    return text[1:-1] if text.startswith("(") and text.endswith(")") else text


def translate_program(program: ast.Program, schema: Schema) -> TranslationResult:
    return _Translator(schema).program(program)
