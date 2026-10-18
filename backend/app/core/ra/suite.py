"""Build a question's test databases once, when staff save it, and measure how strong they are.

The suite is grown until it catches every deliberately wrong version (mutant, see
mutate.py) of the model answer:

  1. Start with the empty database.
  2. Draw random databases from the generator (seeded per question). Keep the first
     ``baseline`` of them whatever they do: they guard against mistakes nobody listed.
  3. Keep any further database that catches ("kills") a mutant not caught so far.
  4. Stop when every mutant is killed (and the baseline is full), or the budget runs out.
  5. Add a few larger databases (up to 20 tuples per relation) for mistakes that only
     show with more data.

The result records which mutants were killed. A mutant that survives is shown to staff:
either the data can't tell it apart from the model answer because it is equivalent
(fine), or the schema's constraints/the budget prevented it (worth a look).
"""
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from app.core.ra import ast
from app.core.ra.compare import equal
from app.core.ra.errors import RAError
from app.core.ra.evaluator import EvalOptions, evaluate
from app.core.ra.generator import GenConfig, Generator
from app.core.ra.mutate import mutants as make_mutants
from app.core.ra.printer import program_to_text
from app.core.ra.schema import Database


@dataclass(frozen=True)
class SuiteConfig:
    seed: int = 0
    bag: bool = False
    gen: GenConfig = GenConfig()
    baseline: int = 60
    large: int = 5
    large_rows: int = 20
    max_candidates: int = 3000
    time_budget_s: float = 4.0


@dataclass
class MutantOutcome:
    description: str
    line: Optional[int]
    text: str          # the whole mutated answer, in slide notation
    killed: bool


@dataclass
class TestSuite:
    databases: List[Database]
    mutants: List[MutantOutcome] = field(default_factory=list)
    candidates_tried: int = 0
    build_ms: float = 0.0

    @property
    def killed(self) -> int:
        return sum(m.killed for m in self.mutants)

    def summary(self) -> dict:
        return {"databases": len(self.databases), "mutants": len(self.mutants), "mutants_killed": self.killed,
                "candidates_tried": self.candidates_tried, "build_ms": round(self.build_ms, 1),
                "surviving_mutants": [{"description": m.description, "line": m.line, "text": m.text}
                                      for m in self.mutants if not m.killed]}

    # Stored on the question so every grading uses exactly these databases.
    def to_json(self) -> dict:
        return {"databases": [{t.name: [list(r) for r in t.rows] for t in d.tables} for d in self.databases],
                "mutants": [m.__dict__ for m in self.mutants],
                "candidates_tried": self.candidates_tried, "build_ms": self.build_ms}

    @classmethod
    def from_json(cls, data: dict, schema: Database) -> "TestSuite":
        dbs = [schema.with_rows({k: [tuple(r) for r in v] for k, v in d.items()}) for d in data["databases"]]
        return cls(dbs, [MutantOutcome(**m) for m in data.get("mutants", [])],
                   data.get("candidates_tried", 0), data.get("build_ms", 0.0))


def question_seed(*parts: str) -> int:
    """A stable seed from the question's own text, so its databases never change by accident."""
    return int.from_bytes(hashlib.sha256("\x00".join(parts).encode()).digest()[:8], "big")


def _final(program: ast.Program, db: Database, options: EvalOptions):
    r = evaluate(program, db, trace=False, options=options)
    return r.columns, r.rows


def build_suite(schema: Database, model: ast.Program, config: SuiteConfig = SuiteConfig(),
                options: EvalOptions = EvalOptions(), hint_programs: Sequence[ast.Program] = ()) -> TestSuite:
    started = time.perf_counter()
    empty = schema.with_rows({})
    # Mutants that cannot even run (e.g. an attribute vanished) are useless for testing.
    candidates, seen_text = [], {program_to_text(model)}
    for m in make_mutants(model):
        text = program_to_text(m.program)
        if text in seen_text:
            continue
        try:
            evaluate(m.program, empty, trace=False, options=options)
        except RAError:
            continue
        seen_text.add(text)
        candidates.append((m, text))
    killed = [False] * len(candidates)

    rng = random.Random(config.seed)
    gen = Generator(schema, [model, *hint_programs], config.gen)
    kept: List[Database] = [empty]
    tried = 0
    try:
        while tried < config.max_candidates and time.perf_counter() - started < config.time_budget_s:
            if all(killed) and len(kept) > config.baseline:
                break
            db = gen.generate(rng)
            tried += 1
            new_kill = _kill(model, candidates, killed, db, options, config.bag)
            if new_kill is None:
                continue
            if new_kill or len(kept) <= config.baseline:
                kept.append(db)
        for _ in range(config.large):
            db = gen.generate(rng, max_rows=config.large_rows)
            if _kill(model, candidates, killed, db, options, config.bag) is not None:
                kept.append(db)
    finally:
        gen.close()

    outcomes = [MutantOutcome(m.description, m.line, text, k) for (m, text), k in zip(candidates, killed)]
    return TestSuite(kept, outcomes, tried, (time.perf_counter() - started) * 1000)


def _kill(model, candidates, killed: List[bool], db: Database, options: EvalOptions, bag: bool) -> Optional[bool]:
    """Mark the mutants this database catches. True if it caught a new one; None if the
    model answer itself cannot run on it (the database is then useless)."""
    try:
        model_cols, model_rows = _final(model, db, options)
    except RAError:
        return None
    new_kill = False
    for i, (m, _text) in enumerate(candidates):
        if killed[i]:
            continue
        try:
            cols, rows = _final(m.program, db, options)
        except RAError:
            continue
        if not equal(model_cols, model_rows, cols, rows, bag=bag):
            killed[i] = new_kill = True
    return new_kill
