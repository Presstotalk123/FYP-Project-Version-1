"""Parse relational-algebra programs into the typed tree in ``ast.py``.

A program is a sequence of statements, written as on the course slides:

    R1 := σ School = 'SCSE' CrsSch
    R2 := Π Course R1
    R3 := Π Name, Course (Grades)
    R3 ÷ R2

Statements are separated by ``;`` or by line breaks: a new statement starts on a line
that begins with ``Name :=`` (or ``Name ←``), or when the previous lines already form a
complete statement and the new line doesn't continue it. Expressions may therefore span
several lines. The answer is the last statement (its value, if it is an assignment).

Each statement is parsed with a Lark LALR parser (linear time). ``ρ S (…)`` is
ambiguous: the brackets can hold S's new attribute names (``ρ S(a, b) R``) or the
relation being renamed (``ρ S (R)``). The grammar reads them as attribute names; when
that leaves the statement unparseable, the statement is parsed again with the brackets
read as the relation (see ``_rename_retries``).
"""
import os
import re
from functools import lru_cache
from typing import Iterable, List, Tuple

from lark import Lark, Transformer, v_args
from lark.exceptions import UnexpectedCharacters, UnexpectedEOF, UnexpectedInput, VisitError

from app.core.ra import ast
from app.core.ra import errors as E
from app.core.ra.errors import RAError
from app.core.ra.normalize import normalize, restore_name

MAX_PROGRAM_CHARS = 5000
MAX_STATEMENTS = 30
MAX_DEPTH = 64

_COMP = {"=": "=", "<>": "<>", "!=": "<>", "≠": "<>", "<": "<", ">": ">",
         "<=": "<=", "≤": "<=", ">=": ">=", "≥": ">="}

_TOKEN_WORDS = {
    "NAME": "a name", "LPAR": "“(”", "RPAR": "“)”", "LSQB": "“[”", "RSQB": "“]”",
    "SUB": "“_{”", "RBRACE": "“}”", "COMMA": "“,”", "DOT": "“.”",
    "SELECT": "σ", "PROJECT": "Π", "RENAME": "ρ", "DISTINCT": "δ", "GROUP": "γ",
    "JOIN": "⋈", "LJOIN": "⟕", "RJOIN": "⟖", "FJOIN": "⟗", "CROSS": "×",
    "DIVIDE": "÷", "UNION": "∪", "INTERSECT": "∩", "MINUS": "−", "ASSIGN": ":=",
    "ARROW": "→", "PLUS": "+", "TIMES": "*", "DIVBY": "/", "STAR": "*",
    "AND": "AND", "OR": "OR", "NOT": "NOT", "AGG": "an aggregate (COUNT, SUM, …)",
    "COMP": "a comparison (=, <, ≠ …)", "NUMBER": "a number", "STRING": "a 'string'",
    "$END": "the end of the statement",
}

_NAME = r"[A-Za-z_][A-Za-z0-9_‐]*"
_ASSIGN_START = re.compile(rf"^\s*{_NAME}\s*(:=|←)")
_ENDS_WITH_OPERATOR = re.compile(r"(⋈|⟕|⟖|⟗|×|÷|∪|∩|−|-|:=|←|,|\(|\[|_\{|σ|π|Π|ρ|δ|γ|∧|∨|¬|=|<|>|≤|≥|≠"
                                 r"|\\[a-z]+|\b(?:and|or|not)\b)\s*$", re.IGNORECASE)
_STARTS_WITH_OPERATOR = re.compile(r"^\s*(⋈|⟕|⟖|⟗|×|÷|∪|∩|−|-|\)|,|∧|∨|=|<|>|≤|≥|≠"
                                   r"|\\(join|leftjoin|rightjoin|fulljoin|cross|divide|union|intersect|diff)\b"
                                   r"|(and|or)\b)", re.IGNORECASE)
# "ρ S (" — the start of a rename whose brackets might hold the relation, not attributes.
_RENAME_OPEN = re.compile(rf"(ρ|\\rename)(\s*)({_NAME})(\s*)\(")


@lru_cache(maxsize=1)
def _lark() -> Lark:
    path = os.path.join(os.path.dirname(__file__), "grammar.lark")
    with open(path, encoding="utf-8") as f:
        return Lark(f.read(), parser="lalr", propagate_positions=True, maybe_placeholders=False)


def _pos(meta_or_token) -> ast.Pos:
    return ast.Pos(getattr(meta_or_token, "line", None), getattr(meta_or_token, "column", None))


def _name(tok) -> str:
    return restore_name(str(tok))


def _unquote(text: str) -> str:
    if text[0] == "'":
        return text[1:-1].replace("''", "'")
    return text[1:-1]


@v_args(meta=True)
class _ToAst(Transformer):
    def start(self, meta, items):
        (node,) = items
        if isinstance(node, ast.Statement):
            return node
        return ast.Statement(None, node, _pos(meta))

    def assignment(self, meta, items):
        name, _arrow, expr = items
        return ast.Statement(_name(name), expr, _pos(name))

    def relation(self, meta, items):
        (name,) = items
        return ast.Relation(_name(name), _pos(name))

    def select(self, meta, items):
        _op, cond, child = items
        return ast.Select(cond, child, _pos(meta))

    def project(self, meta, items):
        _op, proj, child = items
        return ast.Project(proj, child, _pos(meta))

    def rename(self, meta, items):
        _op, (relname, attrs), child = items
        return ast.Rename(relname, attrs, child, _pos(meta))

    def distinct(self, meta, items):
        _op, child = items
        return ast.Distinct(child, _pos(meta))

    def group(self, meta, items):
        _op, (group_by, aggregates), child = items
        return ast.Group(group_by, aggregates, child, _pos(meta))

    def _binary(op, with_condition=False):
        def build(self, meta, items):
            if with_condition:
                left, _tok, cond, right = items
            else:
                left, _tok, right = items
                cond = None
            return ast.Binary(op, left, right, cond, _pos(meta))
        return build

    natural_join = _binary("natural_join")
    theta_join = _binary("theta_join", True)
    left_join = _binary("left_join")
    left_theta_join = _binary("left_join", True)
    right_join = _binary("right_join")
    right_theta_join = _binary("right_join", True)
    full_join = _binary("full_join")
    full_theta_join = _binary("full_join", True)
    product = _binary("product")
    division = _binary("division")
    union = _binary("union")
    intersect = _binary("intersect")
    difference = _binary("difference")

    # parameters
    def cond_param(self, meta, items):
        return [i for i in items if not hasattr(i, "type")][0]

    proj_param = rename_param = group_param = cond_param

    def proj_list(self, meta, items):
        return list(items)

    def proj_item(self, meta, items):
        value = items[0]
        alias = _name(items[2]) if len(items) == 3 else None
        return ast.ProjItem(value, alias)

    def _arith(op):
        def build(self, meta, items):
            left, _tok, right = items
            return ast.Arith(op, left, right, _pos(meta))
        return build

    add, sub, mul, div = _arith("+"), _arith("-"), _arith("*"), _arith("/")

    def rename_spec(self, meta, items):
        relname, *attrs = items
        return _name(relname), ([_name(a) for a in attrs] or None)

    def group_list(self, meta, items):
        group_by = [i for i in items if isinstance(i, ast.AttrRef)]
        aggregates = [i for i in items if isinstance(i, ast.Aggregate)]
        return group_by, aggregates

    def group_by(self, meta, items):
        return items[0]

    def aggregate(self, meta, items):
        func, target, _arrow, alias = items
        attr = target if isinstance(target, ast.AttrRef) else None
        return ast.Aggregate(str(func).upper(), attr, _name(alias), _pos(func))

    def attr(self, meta, items):
        if len(items) == 2:
            return ast.AttrRef(_name(items[1]), _name(items[0]), _pos(items[0]))
        return ast.AttrRef(_name(items[0]), None, _pos(items[0]))

    # conditions
    def comparison(self, meta, items):
        left, op, right = items
        return ast.Comparison(left, _COMP[str(op)], right, _pos(meta))

    def and_(self, meta, items):
        return ast.BoolOp("AND", items[0], items[2])

    def or_(self, meta, items):
        return ast.BoolOp("OR", items[0], items[2])

    def not_(self, meta, items):
        return ast.Not(items[1])

    def number(self, meta, items):
        (tok,) = items
        text = str(tok)
        return ast.Literal(float(text) if "." in text else int(text), _pos(tok))

    def negative(self, meta, items):
        _minus, tok = items
        lit = self.number(meta, [tok])
        lit.value = -lit.value
        return lit

    def string(self, meta, items):
        (tok,) = items
        return ast.Literal(_unquote(str(tok)), _pos(tok))

    def aggregate_in_condition(self, meta, items):
        func = items[0]
        raise RAError(E.AGGREGATE_IN_CONDITION,
                      f"Aggregate functions like {str(func).upper()}(…) can only be used inside γ, "
                      "not in a condition.", func.line, func.column,
                      "Compute it first, e.g. R1 := γ MAX(Score) → MaxScore (Quiz1), then join "
                      "with R1 (see the lecture example “student with the highest score”).")


def _describe(expected: Iterable[str]) -> str:
    words = sorted({_TOKEN_WORDS.get(t, t) for t in expected if not t.startswith("__")})
    if not words:
        return ""
    if len(words) > 8:
        return ""
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " or " + words[-1]


def _parse_once(padded: str, line: int, col: int) -> ast.Statement:
    try:
        return _ToAst().transform(_lark().parse(padded))
    except VisitError as e:
        if isinstance(e.orig_exc, RAError):
            raise e.orig_exc from None
        raise
    except UnexpectedCharacters as e:
        raise RAError(E.SYNTAX, f"Unexpected character “{padded[e.pos_in_stream]}”.",
                      e.line, e.column, _hint(e)) from None
    except UnexpectedEOF as e:
        raise RAError(E.SYNTAX, "This statement ends too early.", line, col, _hint(e)) from None
    except UnexpectedInput as e:
        tok = getattr(e, "token", None)
        if tok is None or tok.type == "$END":
            raise RAError(E.SYNTAX, "This statement ends too early.", e.line if e.line > 0 else line,
                          e.column if e.column > 0 else col, _hint(e)) from None
        raise RAError(E.SYNTAX, f"Unexpected “{tok}”.", e.line, e.column, _hint(e)) from None


def _rename_retries(text: str) -> List[str]:
    """Versions of ``text`` where ``ρ S (`` is read as ``ρ[S] (``: brackets hold the relation.

    Each rename is tried on its own, then all of them together. The rewrite keeps the
    text the same length when the student left spaces around S, so positions only shift
    for unusually tight spellings such as ``ρS(R)``.
    """
    matches = list(_RENAME_OPEN.finditer(text))

    def rewrite(m: re.Match) -> str:
        op, w1, name, w2 = m.group(1), m.group(2), m.group(3), m.group(4)
        pad = max(len(w1) + len(w2) - 2, 0)
        return f"{op}[{name}]" + " " * pad + "("

    def apply(chosen) -> str:
        out, last = [], 0
        for m in chosen:
            out.append(text[last:m.start()])
            out.append(rewrite(m))
            last = m.end()
        out.append(text[last:])
        return "".join(out)

    tries = [apply([m]) for m in matches]
    if len(matches) > 1:
        tries.append(apply(matches))
    return tries


def _parse_statement(text: str, line: int, col: int) -> ast.Statement:
    """Parse one statement, keeping line/column positions absolute."""
    padded = "\n" * (line - 1) + " " * (col - 1) + text
    try:
        return _parse_once(padded, line, col)
    except RAError as first_error:
        if first_error.code != E.SYNTAX:
            raise
        for retry in _rename_retries(padded):
            try:
                return _parse_once(retry, line, col)
            except RAError:
                continue
        raise


def _hint(e: UnexpectedInput):
    expected = getattr(e, "expected", None) or getattr(e, "allowed", None) or []
    described = _describe(expected)
    return f"Expected {described}." if described else None


def _parses(text: str, line: int, col: int) -> bool:
    try:
        _parse_statement(text, line, col)
        return True
    except RAError:
        return False


def split_statements(text: str) -> List[Tuple[str, int, int]]:
    """Split a program into (statement text, line, column) chunks."""
    # 1. split on semicolons outside strings
    pieces: List[Tuple[str, int, int]] = []
    buf, line, col, start = [], 1, 1, (1, 1)
    quote = None
    closers = {"'": "'", "‘": "’", '"': '"', "“": "”"}
    for ch in text:
        if quote:
            if ch == closers[quote]:
                quote = None
        elif ch in closers:
            quote = ch
        if ch == ";" and not quote:
            pieces.append(("".join(buf), *start))
            buf = []
            start = (line, col + 1)
        else:
            buf.append(ch)
        if ch == "\n":
            line, col = line + 1, 1
            if not buf or "".join(buf).strip() == "":
                start = (line, 1)
                buf = []
        else:
            col += 1
    pieces.append(("".join(buf), *start))

    # 2. split each piece on line breaks where a new statement begins
    out: List[Tuple[str, int, int]] = []
    for piece, pline, pcol in pieces:
        if not piece.strip():
            continue
        lines = piece.split("\n")
        current: List[str] = []
        cur_line, cur_col = pline, pcol
        for i, ln in enumerate(lines):
            this_line = pline + i
            this_col = pcol if i == 0 else 1
            stripped = re.sub(r"(--|//).*$", "", ln)
            if current and stripped.strip():
                prev = "\n".join(current)
                prev_code = re.sub(r"(--|//)[^\n]*", "", prev).rstrip()
                depth = prev_code.count("(") - prev_code.count(")")
                new_statement = depth <= 0 and not _ENDS_WITH_OPERATOR.search(prev_code) and (
                    _ASSIGN_START.match(stripped)
                    or (not _STARTS_WITH_OPERATOR.match(stripped) and _parses(prev, cur_line, cur_col)))
                if new_statement:
                    out.append((prev, cur_line, cur_col))
                    current, cur_line, cur_col = [], this_line, this_col
            if not current and not stripped.strip():
                cur_line = this_line + 1
                cur_col = 1
                continue
            if not current:
                cur_line, cur_col = this_line, this_col
            current.append(ln)
        if current and "\n".join(current).strip():
            out.append(("\n".join(current), cur_line, cur_col))
    return out


def parse(text: str, names: Iterable[str] = ()) -> ast.Program:
    """Parse an RA program. Raises RAError (RA001 syntax, RA009 too large/deep, RA013 …).

    ``names`` are the schema's relation and attribute names; pass them so names that
    contain "-" (teamid-one) are read as one name.
    """
    if len(text) > MAX_PROGRAM_CHARS:
        raise RAError(E.TOO_COMPLEX, f"The answer is too long (max {MAX_PROGRAM_CHARS} characters).")
    text = normalize(text, names)
    chunks = split_statements(text)
    if not chunks:
        raise RAError(E.SYNTAX, "The answer is empty.", 1, 1)
    if len(chunks) > MAX_STATEMENTS:
        raise RAError(E.TOO_COMPLEX, f"Too many statements (max {MAX_STATEMENTS}).")
    statements = [_parse_statement(chunk, line, col) for chunk, line, col in chunks]
    for s in statements:
        if ast.depth(s.expr) > MAX_DEPTH:
            raise RAError(E.TOO_COMPLEX, f"Expression is nested too deeply (max {MAX_DEPTH} levels).",
                          s.pos.line, s.pos.col)
    for s in statements[:-1]:
        if s.name is None:
            raise RAError(E.SYNTAX, "Only the last line can be a bare expression; give earlier "
                          "results a name, e.g. R1 := …", s.pos.line, s.pos.col)
    return ast.Program(statements)
