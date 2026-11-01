"""Example data for a question that has none of its own: what students see with the schema.

A question may leave its INSERT box empty (the course tutorials give only a schema). The
grader doesn't need data, but students do want tables to look at and to run their answer
on. So such a question gets one small example database:

  * built by the same generator as the test databases (generator.py), so primary keys,
    foreign keys and CHECK constraints hold, and joins along keys find matches;
  * consistent like real data even when the schema declares no REFERENCES (the
    tutorials don't): attributes named like another relation's key are treated as a
    reference to it (MAJOR.Sid → STUDENT.Sid, ENROLL(Dname, Cno, Sectno) → SECTION), so
    no student is enrolled who doesn't exist. Only here: the test databases deliberately
    keep only the references the schema declares;
  * with realistic-looking values guessed from each attribute's name (example_values.py)
    plus every constant of the model answers, so σ School = 'SCSE' selects something;
  * 3–5 tuples per relation, small enough to trace by hand;
  * chosen from a few hundred candidates as the one that best shows what each part's
    model answer does: its final result is not empty (an empty answer teaches nothing),
    each σ keeps some tuples but not all, each − removes some but not all, as many
    other operators as possible give a non-empty result, and values vary;
  * seeded from the question's text, so the same question always gets the same data.
    ``variant`` picks another one (staff's Regenerate button).

Grading does not use it: verdicts still come from the test databases.
"""
import random
from dataclasses import replace
from typing import List, Optional, Sequence

from app.core.ra import ast
from app.core.ra.errors import RAError
from app.core.ra.evaluator import EvalOptions, evaluate
from app.core.ra.example_values import realistic_values
from app.core.ra.generator import GenConfig, Generator, _parents_first
from app.core.ra.parser import parse
from app.core.ra.schema import Database, ForeignKey
from app.core.ra.suite import question_seed

MIN_ROWS, MAX_ROWS = 3, 5
CANDIDATES = 300
_CONFIG = GenConfig(pool_size=8, max_rows=MAX_ROWS, fk_follow_rate=1.0)


def _with_implied_references(schema: Database) -> Database:
    """The schema plus a reference wherever a relation has every attribute of another
    relation's primary key. Largest keys first, and an attribute takes part in one
    reference only (ENROLL → SECTION, not also → COURSE and → DEPT: SECTION already
    follows COURSE, which follows DEPT)."""
    keyed = sorted((t for t in schema.tables if t.primary_key), key=lambda t: -len(t.primary_key))
    tables = []
    for t in schema.tables:
        fks = list(t.foreign_keys)
        used = {c.casefold() for fk in fks for c in fk.columns}
        own = {c.casefold(): c for c in t.column_names}
        for parent in keyed:
            if parent.name.casefold() == t.name.casefold():
                continue
            key = [k.casefold() for k in parent.primary_key]
            if all(k in own for k in key) and not used & set(key) and not _same_key(t, key):
                fks.append(ForeignKey([own[k] for k in key], parent.name, list(parent.primary_key)))
                used |= set(key)
        tables.append(replace(t, foreign_keys=fks))
    return Database(tables)


def _same_key(t, key: List[str]) -> bool:
    """Two relations with exactly the same key (STUDENT and STUDENT_INFO by Sid) are peers, not parent and child."""
    return sorted(c.casefold() for c in t.primary_key) == sorted(key)


def _programs(db: Database, answers: Sequence[str]) -> List[ast.Program]:
    """The model answers that can be read (a half-written one in the staff form is skipped)."""
    out = []
    for answer in answers:
        try:
            out.append(parse(answer, db.names()))
        except RAError:
            continue
    return out


def _node_score(node: dict) -> int:
    """How well one operator of the model answer is shown by this data (see the module notes)."""
    children = node.get("children") or []
    score = sum(_node_score(c) for c in children)
    count = node.get("row_count", 0)
    op = node.get("op")
    if op == "relation":
        return score
    if op == "select" and children:
        score += 10 if 0 < count < children[0].get("row_count", 0) else 0
    elif op == "difference" and len(children) == 2:
        score += 10 if 0 < count < children[0].get("row_count", 0) else 0
    else:
        score += 3 * bool(count)
    return score


def _score(db: Database, programs: Sequence[ast.Program], options: EvalOptions) -> int:
    """Non-empty final answers count most, then each operator shown well, then variety
    (distinct values in each attribute: not every course called "Algorithms")."""
    score = 0
    for program in programs:
        try:
            result = evaluate(program, db, options=options)
        except RAError:
            continue
        score += 100 * bool(result.rows)
        score += sum(_node_score(s["tree"]) for s in result.statements)
    return score + sum(len({row[i] for row in t.rows}) for t in db.tables for i in range(len(t.columns)))


def build_example(schema_sql: str, model_answers: Sequence[str], *, variant: int = 0,
                  options: EvalOptions = EvalOptions()) -> Database:
    """The example database for a question (raises RAError if the schema is broken)."""
    schema = Database.from_sql(schema_sql)
    programs = _programs(schema, model_answers)
    rng = random.Random(question_seed("example data", schema_sql, *model_answers, str(variant)))
    gen = Generator(_with_implied_references(schema), programs, _CONFIG, values=realistic_values)
    best: Optional[Database] = None
    best_score = -1
    try:
        for _ in range(CANDIDATES):
            linked = gen.generate(rng, max_rows=MAX_ROWS, min_rows=MIN_ROWS)
            db = schema.with_rows({t.name: t.rows for t in linked.tables})      # the schema as declared
            score = _score(db, programs, options)
            if score > best_score:
                best, best_score = db, score
    finally:
        gen.close()
    return best if best is not None else schema


def _literal(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return str(int(v))
    if isinstance(v, (int, float)):
        return repr(v)
    return "'" + str(v).replace("'", "''") + "'"


def _ident(name: str) -> str:
    return name if name.replace("_", "a").isalnum() and not name[0].isdigit() else '"' + name.replace('"', '""') + '"'


def to_insert_sql(db: Database) -> str:
    """INSERT statements for every tuple, parents first so foreign keys hold when run in order."""
    lines = []
    for t in _parents_first(db.tables):
        for row in t.rows:
            lines.append(f"INSERT INTO {_ident(t.name)} VALUES ({', '.join(_literal(v) for v in row)});")
        if t.rows:
            lines.append("")
    return "\n".join(lines).strip() + ("\n" if lines else "")
