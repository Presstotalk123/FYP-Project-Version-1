"""Relational-algebra support: parse RA text and translate it into SQLite SQL.

    from app.core.ra import translate, Schema
    result = translate("π[name](σ[age > 20](Student))", Schema.from_sqlite(db_path))
    result.sql                # SELECT/WITH only — still run through the read-only executor
    result.tree               # JSON tree for the expression-tree view
    result.output_attributes  # column names of the result
    result.operators_used     # e.g. ["select", "project"] → concept tagging
    result.warnings           # RAError objects that do not block execution (RA008)

Errors are raised as ``RAError`` with a code from ``errors.py`` and, where possible,
the line/column to underline in the editor.
"""
from app.core.ra.errors import RAError
from app.core.ra.parser import parse
from app.core.ra.schema import Schema
from app.core.ra.translator import TranslationResult, translate_program


def translate(expression: str, schema: Schema) -> TranslationResult:
    return translate_program(parse(expression), schema)


__all__ = ["translate", "parse", "Schema", "RAError", "TranslationResult"]
