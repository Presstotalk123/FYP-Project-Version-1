"""Parse relational-algebra text into the typed tree in ``ast.py``.

Uses a Lark LALR parser (linear time, no backtracking) built once from
``grammar.lark``. Lark errors are converted into ``RAError(RA001)`` with a
position and a plain-language description of what was expected.
"""
import os
from functools import lru_cache
from typing import Iterable

from lark import Lark, Transformer, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, VisitError

from app.core.ra import ast
from app.core.ra.errors import RAError, SYNTAX, TOO_COMPLEX

MAX_EXPRESSION_CHARS = 5000
MAX_DEPTH = 64

_COMP_CANONICAL = {"=": "=", "<>": "<>", "!=": "<>", "≠": "<>", "<": "<", ">": ">",
                   "<=": "<=", "≤": "<=", ">=": ">=", "≥": ">="}

# How expected tokens are described to students in syntax errors.
_TOKEN_WORDS = {
    "NAME": "a name", "LPAR": "“(”", "RPAR": "“)”", "LSQB": "“[”", "RSQB": "“]”",
    "__ANON_0": "“_{”", "RBRACE": "“}”", "COMMA": "“,”", "SEMICOLON": "“;”", "DOT": "“.”",
    "SELECT": "σ", "PROJECT": "π", "RENAME": "ρ", "JOIN": "⋈", "CROSS": "×",
    "DIVIDE": "÷", "UNION": "∪", "INTERSECT": "∩", "MINUS": "−", "ASSIGN": "←",
    "AND": "and", "OR": "or", "NOT": "not", "COMP": "a comparison (=, <, > …)",
    "SIGNED_NUMBER": "a number", "STRING": "a 'string'", "$END": "the end of the expression",
}


@lru_cache(maxsize=1)
def _parser() -> Lark:
    path = os.path.join(os.path.dirname(__file__), "grammar.lark")
    with open(path, encoding="utf-8") as f:
        return Lark(f.read(), parser="lalr", propagate_positions=True, maybe_placeholders=False)


def _pos(meta_or_token) -> ast.Pos:
    line = getattr(meta_or_token, "line", None)
    col = getattr(meta_or_token, "column", None)
    return ast.Pos(line, col)


def _describe(expected: Iterable[str]) -> str:
    words = sorted({_TOKEN_WORDS.get(t, t) for t in expected})
    if not words:
        return ""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " or " + words[-1]


@v_args(meta=True)
class _ToAst(Transformer):
    # ── expressions ──
    def start(self, meta, items):
        *assignments, result = items
        return ast.Program(list(assignments), result)

    def assignment(self, meta, items):
        name, _arrow, expr = items
        return ast.Assignment(str(name), expr, _pos(name))

    def relation(self, meta, items):
        (name,) = items
        return ast.Relation(str(name), _pos(name))

    def select(self, meta, items):
        _op, cond, child = items
        return ast.Select(cond, child, _pos(meta))

    def project(self, meta, items):
        _op, attrs, child = items
        return ast.Project(attrs, child, _pos(meta))

    def rename(self, meta, items):
        _op, (relname, attrs), child = items
        return ast.Rename(relname, attrs, child, _pos(meta))

    def _binary(op):
        def build(self, meta, items):
            left, _tok, right = items
            return ast.Binary(op, left, right, pos=_pos(meta))
        return build

    natural_join = _binary("natural_join")
    product = _binary("product")
    division = _binary("division")
    union = _binary("union")
    intersect = _binary("intersect")
    difference = _binary("difference")

    def theta_join(self, meta, items):
        left, _tok, cond, right = items
        return ast.Binary("theta_join", left, right, cond, _pos(meta))

    # ── parameters ──
    def cond_param(self, meta, items):
        return items[0]

    def attr_param(self, meta, items):
        return items[0]

    def rename_param(self, meta, items):
        return items[0]

    def attr_list(self, meta, items):
        return list(items)

    def rename_spec(self, meta, items):
        relname, *attrs = items
        return str(relname), ([str(a) for a in attrs] or None)

    def attr(self, meta, items):
        if len(items) == 2:
            return ast.AttrRef(str(items[1]), str(items[0]), _pos(items[0]))
        return ast.AttrRef(str(items[0]), None, _pos(items[0]))

    # ── conditions ──
    def comparison(self, meta, items):
        left, op, right = items
        return ast.Comparison(left, _COMP_CANONICAL[str(op)], right, _pos(meta))

    def and_(self, meta, items):
        return ast.BoolOp("AND", items[0], items[2])

    def or_(self, meta, items):
        return ast.BoolOp("OR", items[0], items[2])

    def not_(self, meta, items):
        return ast.Not(items[1])

    def number(self, meta, items):
        (tok,) = items
        text = str(tok)
        value = float(text) if any(c in text for c in ".eE") else int(text)
        return ast.Literal(value, _pos(tok))

    def string(self, meta, items):
        (tok,) = items
        return ast.Literal(str(tok)[1:-1].replace("''", "'"), _pos(tok))


def parse(text: str) -> ast.Program:
    """Parse RA text. Raises RAError (RA001 syntax, RA009 too large/deep)."""
    if len(text) > MAX_EXPRESSION_CHARS:
        raise RAError(TOO_COMPLEX, f"Expression is too long (max {MAX_EXPRESSION_CHARS} characters).")
    if not text.strip():
        raise RAError(SYNTAX, "The expression is empty.", 1, 1)
    try:
        tree = _parser().parse(text)
        program = _ToAst().transform(tree)
    except UnexpectedCharacters as e:
        raise RAError(SYNTAX, f"Unexpected character “{text[e.pos_in_stream]}”.", e.line, e.column,
                      _expected_hint(e)) from None
    except UnexpectedEOF as e:
        raise RAError(SYNTAX, "The expression ends too early.", None, None,
                      _expected_hint(e)) from None
    except UnexpectedInput as e:
        tok = getattr(e, "token", None)
        found = "the end of the expression" if tok is None or tok.type == "$END" else f"“{tok}”"
        raise RAError(SYNTAX, f"Unexpected {found}.", e.line, e.column, _expected_hint(e)) from None
    except VisitError as e:  # pragma: no cover - transformer bug, not user error
        raise e.orig_exc

    for node in [a.expr for a in program.assignments] + [program.result]:
        if ast.depth(node) > MAX_DEPTH:
            raise RAError(TOO_COMPLEX, f"Expression is nested too deeply (max {MAX_DEPTH} levels).")
    return program


def _expected_hint(e: UnexpectedInput):
    expected = getattr(e, "expected", None) or getattr(e, "allowed", None) or []
    described = _describe(expected)
    return f"Expected {described}." if described else None
