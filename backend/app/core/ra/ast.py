"""Typed syntax tree for relational-algebra expressions.

Every node records the line/column where it starts so errors can point at the exact
place in the student's editor.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


@dataclass
class Pos:
    line: Optional[int] = None
    col: Optional[int] = None


# ── conditions ────────────────────────────────────────────────────────────────
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
            return "'" + self.value.replace("'", "''") + "'"
        return str(self.value)


@dataclass
class Comparison:
    left: Union[AttrRef, Literal]
    op: str          # canonical SQL operator: = <> < <= > >=
    right: Union[AttrRef, Literal]
    pos: Pos = field(default_factory=Pos)

    def __str__(self) -> str:
        return f"{self.left} {self.op} {self.right}"


@dataclass
class BoolOp:
    op: str          # AND | OR
    left: "Condition"
    right: "Condition"

    def __str__(self) -> str:
        return f"({self.left} {self.op.lower()} {self.right})"


@dataclass
class Not:
    operand: "Condition"

    def __str__(self) -> str:
        return f"not ({self.operand})"


Condition = Union[Comparison, BoolOp, Not]


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
class Project:
    attributes: List[AttrRef]
    child: "Expr"
    pos: Pos = field(default_factory=Pos)


@dataclass
class Rename:
    relation: str
    attributes: Optional[List[str]]
    child: "Expr"
    pos: Pos = field(default_factory=Pos)


@dataclass
class Binary:
    """Product, joins, set operations and division."""
    op: str          # product | natural_join | theta_join | union | intersect | difference | division
    left: "Expr"
    right: "Expr"
    condition: Optional[Condition] = None   # theta_join only
    pos: Pos = field(default_factory=Pos)


Expr = Union[Relation, Select, Project, Rename, Binary]


@dataclass
class Assignment:
    name: str
    expr: Expr
    pos: Pos = field(default_factory=Pos)


@dataclass
class Program:
    assignments: List[Assignment]
    result: Expr


def depth(node) -> int:
    """Height of an expression tree (used for the complexity limit)."""
    if isinstance(node, (Select, Project, Rename)):
        return 1 + depth(node.child)
    if isinstance(node, Binary):
        return 1 + max(depth(node.left), depth(node.right))
    return 1


def children(node) -> Tuple:
    if isinstance(node, (Select, Project, Rename)):
        return (node.child,)
    if isinstance(node, Binary):
        return (node.left, node.right)
    return ()
