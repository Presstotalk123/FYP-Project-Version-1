"""Turn a schema written as plain text into CREATE TABLE statements.

Staff write a schema the way the tutorials print it, one relation per line, with each key
attribute marked by ``*``:

    STUDENT(*Sid, Sname, Sex, Age, Year, GPA)
    ENROLL(*Sid, Grade, *Dname, *Cno, *Sectno)

and get SQL they can still edit before saving. A relation starts a line (after any bullet
or number) or follows another relation on the same line, and may span lines; everything
else (backticks, bold, sentences such as "Find the name(s) of …") is ignored.

  * Types are guessed from attribute names (Sid → INTEGER, GPA → REAL, otherwise TEXT),
    unless written after the name: ``GPA REAL`` or ``GPA: REAL``.
  * With ``link_keys``, an attribute group that matches another relation's whole key, by
    name, becomes a foreign key to it: the tutorials' convention ("foreign keys refer to
    primary keys in other tables which have the same attribute names"). Left out where the
    parent is unclear: two relations with the same key (STUDENT(*Sid, …), GRAD(*Sid, …)),
    and relationship relations whose key is only other relations' keys (MAJOR(*Dname, *Sid)
    is not the parent of ENROLL, though ENROLL has both). Generated test data then respects the links (no professor in a department
    that doesn't exist), so staff can untick it when a question needs dangling values.
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.core.ra.errors import INVALID_SCHEMA, RAError

_RELATION = re.compile(r"([A-Za-z_][\w\-]*)\s*\(([^()]*)\)")
_NAME = re.compile(r"[A-Za-z_][\w\-]*")
# What may come before a relation on its line: a bullet or number, or the previous relation and a comma.
_LEAD = re.compile(r"[\s>]*(?:[-*+]|\d+[.)])?[\s,;]*")
_TYPES = {"INTEGER", "INT", "REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL", "TEXT", "VARCHAR", "CHAR",
          "STRING", "DATE", "BOOLEAN"}
_INTEGER = re.compile(r"(id|num|no|nr|number|count|qty|quantity|age|year|level|rank|ssn)$|^num",
                      re.IGNORECASE)
_REAL = re.compile(r"gpa|grade|score|mark|price|salary|amount|cost|rate|balance|weight|height|avg|fee",
                   re.IGNORECASE)


@dataclass
class Relation:
    name: str
    attributes: List[Tuple[str, str]]          # (name, SQL type)
    key: List[str]
    links: List[Tuple[List[str], str, List[str]]] = field(default_factory=list)   # (columns, table, columns)


def guess_type(attribute: str) -> str:
    if _INTEGER.search(attribute):
        return "INTEGER"
    if _REAL.search(attribute):
        return "REAL"
    return "TEXT"


def parse_text_schema(text: str) -> List[Relation]:
    """The relations in ``text``; ``RAError`` (RA020, with line and column) if one can't be read."""
    clean = text.replace("`", " ").replace("**", "  ")
    relations: List[Relation] = []
    seen = set()
    previous_end = 0
    for m in _RELATION.finditer(clean):
        start = max(clean.rfind("\n", 0, m.start()) + 1, previous_end)
        if not _LEAD.fullmatch(clean, start, m.start()):
            continue                    # inside a sentence, e.g. "the name(s) of student(s)"
        previous_end = m.end()
        name = m.group(1)
        line, col = _where(clean, m.start(1))
        if name.casefold() in seen:
            raise RAError(INVALID_SCHEMA, f"Relation {name} is written twice.", line, col)
        seen.add(name.casefold())
        attributes, key, names = [], [], set()
        offset = m.start(2)
        for raw in m.group(2).split(","):
            item = raw.strip()
            a_line, a_col = _where(clean, offset + len(raw) - len(raw.lstrip()))
            offset += len(raw) + 1
            if not item:
                raise RAError(INVALID_SCHEMA, f"{name} has an empty attribute (two commas in a row?).", a_line, a_col)
            is_key = item.startswith("*") or item.endswith("*")
            item = item.strip("*").strip()
            attr, declared = _split_type(item)
            if attr is None:
                raise RAError(INVALID_SCHEMA, f"“{item}” in {name} is not an attribute name.", a_line, a_col,
                              hint="Write attributes as names separated by commas, e.g. STUDENT(*Sid, Sname).")
            if attr.casefold() in names:
                raise RAError(INVALID_SCHEMA, f"{name} has attribute {attr} twice.", a_line, a_col)
            names.add(attr.casefold())
            attributes.append((attr, declared or guess_type(attr)))
            if is_key:
                key.append(attr)
        relations.append(Relation(name, attributes, key))
    if not relations:
        raise RAError(INVALID_SCHEMA, "No relations found.", 1, 1,
                      hint="Write one relation per line, e.g. STUDENT(*Sid, Sname, GPA), marking keys with *.")
    return relations


def link_keys(relations: List[Relation]) -> None:
    """Add a foreign key wherever a relation contains another relation's whole key."""
    def key_of(r: Relation) -> Tuple[str, ...]:
        return tuple(sorted(k.casefold() for k in r.key))
    single_keys = {key_of(r)[0] for r in relations if len(r.key) == 1}
    owners: dict = {}
    for r in relations:
        owners.setdefault(key_of(r), []).append(r)
    parents = [r for r in relations
               if r.key and len(owners[key_of(r)]) == 1                  # STUDENT and GRAD both keyed by Sid
               and not (len(r.key) > 1 and set(key_of(r)) <= single_keys)]  # MAJOR(*Dname, *Sid): a relationship
    for child in relations:
        columns = {a.casefold(): a for a, _ in child.attributes}
        for parent in parents:
            if parent is not child and key_of(parent) != key_of(child) and all(k in columns for k in key_of(parent)):
                child.links.append(([columns[k.casefold()] for k in parent.key], parent.name, list(parent.key)))


def sql_from_text(text: str, *, link: bool = True) -> str:
    """CREATE TABLE statements for the schema in ``text``, one line per relation."""
    relations = parse_text_schema(text)
    if link:
        link_keys(relations)
    return "\n".join(_create(r) for r in relations)


def _create(r: Relation) -> str:
    single = {cols[0].casefold(): (table, ref[0]) for cols, table, ref in r.links if len(cols) == 1}
    parts = []
    for attr, sql_type in r.attributes:
        column = f"{_quote(attr)} {sql_type}"
        if r.key == [attr]:
            column += " PRIMARY KEY"
        if attr.casefold() in single:
            table, ref = single[attr.casefold()]
            column += f" REFERENCES {_quote(table)}({_quote(ref)})"
        parts.append(column)
    if len(r.key) > 1:
        parts.append(f"PRIMARY KEY ({_names(r.key)})")
    for cols, table, ref in r.links:
        if len(cols) > 1:
            parts.append(f"FOREIGN KEY ({_names(cols)}) REFERENCES {_quote(table)}({_names(ref)})")
    return f"CREATE TABLE {_quote(r.name)} ({', '.join(parts)});"


def _split_type(item: str) -> Tuple[Optional[str], Optional[str]]:
    """``GPA``, ``GPA REAL`` or ``GPA: REAL`` → (name, type or None); (None, None) if not an attribute."""
    words = item.replace(":", " ").split()
    if len(words) == 1 and _NAME.fullmatch(words[0]):
        return words[0], None
    if len(words) == 2 and _NAME.fullmatch(words[0]) and words[1].upper() in _TYPES:
        return words[0], _sql_type(words[1].upper())
    return None, None


def _sql_type(declared: str) -> str:
    return {"INT": "INTEGER", "FLOAT": "REAL", "DOUBLE": "REAL", "DECIMAL": "NUMERIC", "VARCHAR": "TEXT",
            "CHAR": "TEXT", "STRING": "TEXT", "DATE": "TEXT", "BOOLEAN": "INTEGER"}.get(declared, declared)


def _quote(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z_]\w*", name) else f'"{name}"'


def _names(names: List[str]) -> str:
    return ", ".join(_quote(n) for n in names)


def _where(text: str, index: int) -> Tuple[int, int]:
    line = text.count("\n", 0, index) + 1
    return line, index - (text.rfind("\n", 0, index) + 1) + 1
