"""Turn a parsed RA answer into textbook notation, as LaTeX, one line per statement.

Students type ``R1 := σ Numphds < 50 (DEPT)``; the preview shows
``\\text{R1} \\leftarrow \\sigma_{\\text{Numphds} < 50}(\\text{DEPT})``, rendered with
the condition as a subscript. It is printed from the parsed tree, not from the text, so
it shows how the answer was *read*: every σ, Π, ρ, δ and γ brackets exactly the input it
applies to, and binary operands that are themselves binary are bracketed. A student who
meant σ to cover a join sees at once that it covers only the next relation.
"""
from typing import List

from app.core.ra import ast

_BINARY = {"product": r"\times", "natural_join": r"\bowtie", "theta_join": r"\bowtie",
           "left_join": r"\mathbin{\text{⟕}}", "right_join": r"\mathbin{\text{⟖}}",
           "full_join": r"\mathbin{\text{⟗}}", "union": r"\cup", "intersect": r"\cap",
           "difference": "-", "division": r"\div", "division_any": r"\div_{\text{any}}"}
_COMPARE = {"=": "=", "<>": r"\neq", "<": "<", "<=": r"\leq", ">": ">", ">=": r"\geq"}
_ARITH = {"+": "+", "-": "-", "*": r"\cdot", "/": "/"}
_ESCAPE = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "_": r"\_", "^": r"\^{}", "#": r"\#",
           "$": r"\$", "%": r"\%", "&": r"\&", "~": r"\~{}"}


def program_to_latex(program: ast.Program) -> List[dict]:
    """``[{"line": n, "name": "R1" | None, "latex": "..."}]``, one entry per statement."""
    out = []
    for s in program.statements:
        body = expr(s.expr)
        latex = rf"{_name(s.name)} \leftarrow {body}" if s.name else body
        out.append({"line": s.pos.line, "name": s.name, "latex": latex})
    return out


def expr(e) -> str:
    if isinstance(e, ast.Relation):
        return _name(e.name)
    if isinstance(e, ast.Select):
        return rf"\sigma_{{{condition(e.condition)}}}({expr(e.child)})"
    if isinstance(e, ast.Project):
        items = ", ".join(_proj_item(i) for i in e.items)
        return rf"\Pi_{{{items}}}({expr(e.child)})"
    if isinstance(e, ast.Rename):
        attrs = f"({', '.join(_name(a) for a in e.attributes)})" if e.attributes else ""
        return rf"\rho_{{{_name(e.relation)}{attrs}}}({expr(e.child)})"
    if isinstance(e, ast.Distinct):
        return rf"\delta({expr(e.child)})"
    if isinstance(e, ast.Group):
        items = [value(g) for g in e.group_by] + [_aggregate(a) for a in e.aggregates]
        return rf"\gamma_{{{', '.join(items)}}}({expr(e.child)})"
    op = _BINARY[e.op]
    if e.condition is not None:
        op = rf"{op}_{{{condition(e.condition)}}}"
    return rf"{_side(e.left)} {op} {_side(e.right)}"


def condition(c) -> str:
    if isinstance(c, ast.Comparison):
        return f"{value(c.left)} {_COMPARE.get(c.op, c.op)} {value(c.right)}"
    if isinstance(c, ast.BoolOp):
        op = r"\land" if c.op == "AND" else r"\lor"
        return f"{_bool_side(c.left, c.op)} {op} {_bool_side(c.right, c.op)}"
    return rf"\lnot ({condition(c.operand)})"


def value(v) -> str:
    if isinstance(v, ast.AttrRef):
        return _name(f"{v.qualifier}.{v.name}" if v.qualifier else v.name)
    if isinstance(v, ast.Literal):
        if isinstance(v.value, str):
            return rf"\text{{‘{_escape(v.value)}’}}"
        return str(v.value)
    return f"{value(v.left)} {_ARITH.get(v.op, v.op)} {value(v.right)}"


def _proj_item(i: ast.ProjItem) -> str:
    return rf"{value(i.value)} \rightarrow {_name(i.alias)}" if i.alias else value(i.value)


def _aggregate(a: ast.Aggregate) -> str:
    attr = value(a.attr) if a.attr is not None else "*"
    return rf"\text{{{a.func}}}({attr}) \rightarrow {_name(a.alias)}"


def _side(e) -> str:
    return f"({expr(e)})" if isinstance(e, ast.Binary) else expr(e)


def _bool_side(c, parent_op: str) -> str:
    return f"({condition(c)})" if isinstance(c, ast.BoolOp) and c.op != parent_op else condition(c)


def _name(name: str) -> str:
    return rf"\text{{{_escape(name)}}}"


def _escape(text: str) -> str:
    return "".join(_ESCAPE.get(ch, ch) for ch in text)
