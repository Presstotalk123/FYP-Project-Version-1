"""The three ways a question can ask for its answer, and moving a model answer between them.

The professor chooses one type for the whole question (students never choose, they
just see the question laid out that way):

  mixed         today's setup: one editor; the answer may be written in steps
                (R1 := …) or as one expression; graded on the final result.
  final_answer  one expression only (no R1 := steps), graded on that expression.
  multi_step    the professor lists the steps, each with a prompt, a model answer and
                marks; students fill in one box per step (step_marking.py marks them).

A multi-step part is stored twice over: its steps (``steps_json``) and, built from them,
an ordinary model answer ``R1 := …`` whose checkpoints are the steps' prompts. So the
grader, the test databases and the analytics work on it unchanged.

Changing the type converts each part's model answer:
  mixed → final_answer      the steps are substituted into one expression (``join``)
  mixed → multi_step        each statement becomes a step (``split``); a single
                            expression becomes one step (no automatic splitting)
  multi_step → mixed        the steps become the R1 := lines (``steps_program``)
  multi_step → final_answer both of those
"""
import re
from dataclasses import dataclass, fields, is_dataclass, replace
from typing import Dict, List, Optional, Sequence

from app.core.ra import ast
from app.core.ra.errors import RAError
from app.core.ra import errors as E
from app.core.ra.parser import parse
from app.core.ra.printer import expr_to_text

MIXED, FINAL_ANSWER, MULTI_STEP = "mixed", "final_answer", "multi_step"
FORMATS = (MIXED, FINAL_ANSWER, MULTI_STEP)
MIN_STEPS, MAX_STEPS = 2, 10

STEP_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
# A line that starts a named step, as the parser reads it (parser._ASSIGN_START).
_ASSIGNMENT = re.compile(r"^\s*[A-Za-z_][\w\-]*\s*(:=|←)", re.MULTILINE)


@dataclass
class Step:
    """One step of a multi-step part. The last step is the final answer and has no name."""
    name: Optional[str]
    prompt: str
    marks: int
    model_answer: str

    def to_dict(self) -> dict:
        return dict(name=self.name, prompt=self.prompt, marks=self.marks, model_answer=self.model_answer)


def steps_from_json(items: Sequence[dict]) -> List[Step]:
    out = [Step(i.get("name"), i.get("prompt") or "", int(i.get("marks") or 0), i.get("model_answer") or "")
           for i in items]
    if out:
        out[-1].name = None
    return out


def default_step_name(index: int) -> str:
    return f"R{index + 1}"


# ── checking an answer's format ──────────────────────────────────────────────
def has_steps(text: str) -> bool:
    """Whether an answer is written in steps (some line starts ``Name :=``) or has
    several statements (``;``). Cheap and lenient: the parser has the final word."""
    return bool(_ASSIGNMENT.search(text or ""))


def single_expression(text: str, names) -> ast.Expr:
    """The one expression ``text`` is, or RAError if it is written in steps."""
    program = parse(text, names)
    if len(program.statements) != 1 or program.statements[0].name is not None:
        first = program.statements[0]
        raise RAError(E.INVALID_ASSIGNMENT, "Write this as one expression, without steps (R1 := …). "
                      "Brackets let one expression hold everything.", first.pos.line, first.pos.col)
    return program.statements[0].expr


# ── multi-step ↔ program ─────────────────────────────────────────────────────
def steps_program(steps: Sequence[Step]) -> str:
    """The model answer a list of steps stands for: ``R1 := …`` lines, then the final step."""
    lines = []
    for i, s in enumerate(steps):
        body = s.model_answer.strip()
        lines.append(body if i == len(steps) - 1 else f"{s.name} := {body}")
    return ";\n".join(lines)


def steps_checkpoints(steps: Sequence[Step]) -> List[dict]:
    """Each step's prompt as the checkpoint for it (``Show structure`` compares with these)."""
    return [{"statement": None if i == len(steps) - 1 else s.name, "label": s.prompt.strip() or f"step {i + 1}"}
            for i, s in enumerate(steps)]


def split(model_answer: str, names, checkpoints: Optional[Sequence[dict]], marks: int) -> List[Step]:
    """A mixed part's model answer as steps: one per statement, the prompt being that
    statement's checkpoint label when staff wrote one. Marks are shared out equally, the
    rest going to the final step. Raises RAError when the model answer can't be read."""
    program = parse(model_answer, names)
    labels = {(c.get("statement") or "").casefold(): c.get("label") or "" for c in (checkpoints or [])}
    statements = program.statements
    n = len(statements)
    steps = []
    for i, s in enumerate(statements):
        final = i == n - 1
        key = "" if final else (s.name or "").casefold()
        label = labels.get(key, "")
        if not label and final and s.name:
            label = labels.get(s.name.casefold(), "")
        if label.startswith("step ") and label.endswith(" of the model solution") or label == "the final answer":
            label = ""                   # the made-up default labels are no prompt
        steps.append(Step(None if final else s.name, label, 0, expr_to_text(s.expr)))
    share, rest = divmod(max(marks, 1), n)
    for i, s in enumerate(steps):
        s.marks = share + (rest if i == n - 1 else 0)
    # Later steps may use the final statement's name (Answer := …): never, it is last.
    return steps


# ── program → one expression ─────────────────────────────────────────────────
def _qualifiers(node, out: set) -> set:
    """Every ``X`` used as ``X.attr`` anywhere in the tree."""
    if isinstance(node, ast.AttrRef):
        if node.qualifier:
            out.add(node.qualifier.casefold())
        return out
    if isinstance(node, (list, tuple)):
        for item in node:
            _qualifiers(item, out)
        return out
    if is_dataclass(node):
        for f in fields(node):
            if f.name != "pos":
                _qualifiers(getattr(node, f.name), out)
    return out


def _substitute(expr, defined: Dict[str, ast.Expr]):
    """``expr`` with each name of an earlier step replaced by that step's expression."""
    if isinstance(expr, ast.Relation):
        return defined.get(expr.name.casefold(), expr)
    if isinstance(expr, ast.Binary):
        return replace(expr, left=_substitute(expr.left, defined), right=_substitute(expr.right, defined))
    if isinstance(expr, (ast.Select, ast.Project, ast.Rename, ast.Distinct, ast.Group)):
        return replace(expr, child=_substitute(expr.child, defined))
    return expr


def join_program(program: ast.Program, *, keep_names: bool = False) -> ast.Expr:
    """The program as one expression. A step whose name is used to qualify attributes
    (R1.MinGPA) keeps its name as ρ R1 (…); with ``keep_names`` every step does."""
    used = _qualifiers(program.statements, set())
    defined: Dict[str, ast.Expr] = {}
    expr = None
    for s in program.statements:
        expr = _substitute(s.expr, defined)
        if s.name:
            key = s.name.casefold()
            if keep_names or key in used:
                defined[key] = ast.Rename(s.name, None, expr)
            else:
                defined[key] = expr
    return expr


def join(model_answer: str, names) -> str:
    """A model answer written in steps, as one expression (the text is unchanged if it
    already is one). Raises RAError when the answer can't be read."""
    program = parse(model_answer, names)
    if len(program.statements) == 1 and program.statements[0].name is None:
        return model_answer
    return expr_to_text(join_program(program))
