"""Typed syntax tree for relational-algebra programs.

Every node records where it starts (line, column) so errors can point at the exact
place in the student's editor.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


@dataclass
class Pos:
    line: Optional[int] = None
    col: Optional[int] = None


# ── values used in conditions and extended projection ─────────────────────────
@dataclass
class AttrRef:
    name: str
    qualifier: Optional[str] = None
    pos: Pos = field(default_factory=Pos)

    def __str__(self) -> str:
        return f"{self.qualifier}.{self.name}" if self.qualifier else self.name


@dataclass
class Literal:
    value: Union[int, float, str]
    pos: Pos = field(default_factory=Pos)

    def __str__(self) -> str:
        if isinstance(self.value, str):
            return "'" + self.value + "'"
        return str(self.value)


@dataclass
class Arith:
    op: str          # + - * /
    left: "Value"
    right: "Value"
    pos: Pos = field(default_factory=Pos)

    def __str__(self) -> str:
        return f"{self.left} {self.op} {self.right}"


Value = Union[AttrRef, Literal, Arith]


@dataclass
class Comparison:
    left: Value
    op: str          # = <> < <= > >=
    right: Value
    pos: Pos = field(default_factory=Pos)

    def __str__(self) -> str:
        return f"{self.left} {_SHOW_OP.get(self.op, self.op)} {self.right}"


_SHOW_OP = {"<>": "≠", "<=": "≤", ">=": "≥"}


@dataclass
class BoolOp:
    op: str          # AND | OR
    left: "Condition"
    right: "Condition"

    def __str__(self) -> str:
        return f"{_paren(self.left, self.op)} {self.op} {_paren(self.right, self.op)}"


@dataclass
class Not:
    operand: "Condition"

    def __str__(self) -> str:
        return f"NOT ({self.operand})"


Condition = Union[Comparison, BoolOp, Not]


def _paren(cond, parent_op: str) -> str:
    if isinstance(cond, BoolOp) and cond.op != parent_op:
        return f"({cond})"
    return str(cond)


# ── relational expressions ────────────────────────────────────────────────────
@dataclass
class Relation:
    name: str
    pos: Pos = field(default_factory=Pos)


@dataclass
class Select:
    condition: Condition
    child: "Expr"
    pos: Pos = field(default_factory=Pos)


@dataclass
class ProjItem:
    value: Value
    alias: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.value} → {self.alias}" if self.alias else str(self.value)


@dataclass
class Project:
    items: List[ProjItem]
    child: "Expr"
    pos: Pos = field(default_factory=Pos)


@dataclass
class Rename:
    relation: str
    attributes: Optional[List[str]]
    child: "Expr"
    pos: Pos = field(default_factory=Pos)


@dataclass
class Distinct:
    child: "Expr"
    pos: Pos = field(default_factory=Pos)


@dataclass
class Aggregate:
    func: str                    # COUNT SUM AVG MIN MAX
    attr: Optional[AttrRef]      # None for COUNT(*)
    alias: str
    pos: Pos = field(default_factory=Pos)

    def __str__(self) -> str:
        return f"{self.func}({self.attr or '*'}) → {self.alias}"


@dataclass
class Group:
    group_by: List[AttrRef]
    aggregates: List[Aggregate]
    child: "Expr"
    pos: Pos = field(default_factory=Pos)


# product | natural_join | theta_join | left_join | right_join | full_join |
# union | intersect | difference | division.  Outer joins carry a condition when
# written with one (⟕ cond), otherwise they join on the common attributes.
@dataclass
class Binary:
    op: str
    left: "Expr"
    right: "Expr"
    condition: Optional[Condition] = None
    pos: Pos = field(default_factory=Pos)


Expr = Union[Relation, Select, Project, Rename, Distinct, Group, Binary]


@dataclass
class Statement:
    """``name := expr`` (name set) or a bare expression (name None)."""
    name: Optional[str]
    expr: Expr
    pos: Pos = field(default_factory=Pos)


@dataclass
class Program:
    statements: List[Statement]

    @property
    def result(self) -> Statement:
        return self.statements[-1]


def children(node) -> Tuple:
    if isinstance(node, (Select, Project, Rename, Distinct, Group)):
        return (node.child,)
    if isinstance(node, Binary):
        return (node.left, node.right)
    return ()


def depth(node) -> int:
    kids = children(node)
    return 1 + (max(depth(k) for k in kids) if kids else 0)
