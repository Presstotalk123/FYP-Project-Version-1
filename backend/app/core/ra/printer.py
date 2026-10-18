"""Turn a parsed RA tree back into the slide notation.

Used to show staff the deliberately wrong versions of a model answer that the grader
tests itself against (mutate.py). The output always parses back to the same tree:
operands of binary operators that are themselves binary get brackets, and σ, Π, ρ, δ, γ
bracket anything that is not a plain relation name.
"""
from app.core.ra import ast

_SYMBOL = {"product": "×", "natural_join": "⋈", "theta_join": "⋈", "left_join": "⟕",
           "right_join": "⟖", "full_join": "⟗", "union": "∪", "intersect": "∩",
           "difference": "−", "division": "÷", "division_any": "÷ₐₙᵧ"}


def expr_to_text(e) -> str:
    if isinstance(e, ast.Relation):
        return e.name
    if isinstance(e, ast.Select):
        return f"σ {e.condition} {_operand(e.child)}"
    if isinstance(e, ast.Project):
        return f"Π {', '.join(str(i) for i in e.items)} {_operand(e.child)}"
    if isinstance(e, ast.Rename):
        attrs = f"({', '.join(e.attributes)})" if e.attributes else ""
        return f"ρ {e.relation}{attrs} {_operand(e.child)}"
    if isinstance(e, ast.Distinct):
        return f"δ {_operand(e.child)}"
    if isinstance(e, ast.Group):
        items = [str(g) for g in e.group_by] + [str(a) for a in e.aggregates]
        return f"γ {', '.join(items)} {_operand(e.child)}"
    cond = f" {e.condition}" if e.condition is not None else ""
    return f"{_side(e.left)} {_SYMBOL[e.op]}{cond} {_side(e.right)}"


def _operand(e) -> str:
    """The input of a unary operator: a bare name, or anything else in brackets."""
    return e.name if isinstance(e, ast.Relation) else f"({expr_to_text(e)})"


def _side(e) -> str:
    """An operand of a binary operator: unary operators bind tighter, so only binary ones need brackets."""
    return f"({expr_to_text(e)})" if isinstance(e, ast.Binary) else expr_to_text(e)


def program_to_text(program: ast.Program) -> str:
    return "\n".join(f"{s.name} := {expr_to_text(s.expr)}" if s.name else expr_to_text(s.expr)
                     for s in program.statements)
