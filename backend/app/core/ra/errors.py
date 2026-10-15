"""Relational-algebra errors, reported in RA terms rather than as raw SQLite messages.

Codes follow the catalogue in FYP Design Document 02, §5.5.
"""
from dataclasses import dataclass, field
from typing import Optional

SYNTAX = "RA001"
UNKNOWN_RELATION = "RA002"
UNKNOWN_ATTRIBUTE = "RA003"
AMBIGUOUS_ATTRIBUTE = "RA004"
UNION_INCOMPATIBLE = "RA005"
INVALID_DIVISION = "RA006"
RENAME_ARITY = "RA007"
TYPE_MISMATCH = "RA008"          # warning only
TOO_COMPLEX = "RA009"
DUPLICATE_ATTRIBUTE = "RA010"
SAME_NAME_INPUTS = "RA011"
INVALID_ASSIGNMENT = "RA012"


@dataclass
class RAError(Exception):
    code: str
    message: str
    line: Optional[int] = None
    col: Optional[int] = None
    hint: Optional[str] = field(default=None)

    def __str__(self) -> str:
        where = f"Line {self.line}, col {self.col}: " if self.line else ""
        hint = f" {self.hint}" if self.hint else ""
        return f"{where}{self.message}{hint}"

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "line": self.line,
                "col": self.col, "hint": self.hint}
