"""Grade a student's RA answer against the model answer, and give feedback on each step.

``PreparedQuestion`` does the per-question work once (parse the model answer, build or
load the test databases, run the model answer on all of them). ``grade`` then checks
one student answer:

  1. Parse it, and run it on the empty schema: errors such as an unknown attribute show
     up here, with line/column.                                → invalid_expression
  2. Its final attributes must be the model answer's (any order). → wrong_columns
  3. If the question has data: same result on it?             → wrong_result
  4. If both answers use only σ(=), Π, ⋈, ×, ρ, ∪: decide exactly with the
     Chandra–Merlin test (conjunctive.py).                    → correct / wrong_in_general
  5. Otherwise run it on every test database (plus a few made for the constants only
     the student used, so a hard-coded value is caught).      → correct / wrong_in_general

Every wrong verdict after step 2 comes with the smallest database found on which the two
answers differ (shrink.py).

Step feedback ("Show structure"): every statement of the student's answer is compared,
**by content, not by name**, with the model answer's checkpoint steps on all test
databases:
  match  — same tuples as a checkpoint on every test database (attribute names may
           differ when the tuples match column for column)
  close  — the same attributes **and the same shape** as a checkpoint (the same
           operators on the same relations, ignoring conditions and constants), but
           different tuples on some test database (that small database is offered).
           E.g. σ Dname = 'Computer Science' where the model has 'Civil Engineering',
           or γ MAX where it has γ MIN. Same attributes alone is not enough: a valid
           different method has many steps that share attributes with the model's.
  none   — matches no checkpoint, which is fine for a different but valid method
"""
import itertools
import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from app.core.ra import ast
from app.core.ra.compare import compare, equal, norm_row, same_columns
from app.core.ra.conjunctive import NotConjunctive, prove, to_ucq
from app.core.ra.errors import RAError
from app.core.ra.evaluator import EvalOptions, Rel, evaluate
from app.core.ra.generator import GenConfig, Generator, collect_hints
from app.core.ra.parser import parse
from app.core.ra.printer import expr_to_text
from app.core.ra.schema import Database
from app.core.ra.shrink import describe, prettify, shrink
from app.core.ra.suite import SuiteConfig, TestSuite, build_suite, question_seed

EXTRA_DATABASES = 60          # made per submission when the student uses constants the model doesn't
MAX_CLOSE_CASES = 3           # "close" steps that get a small example database


@dataclass
class Checkpoint:
    statement: Optional[str]  # the model statement's name; None = the final answer
    label: str


@dataclass
class StepFeedback:
    name: Optional[str]
    line: Optional[int]
    text: str
    columns: List[str]
    status: str                               # match | close | none
    checkpoint: Optional[str] = None          # the checkpoint's label
    renamed: bool = False                     # matched with different attribute names
    case: Optional[dict] = None               # for "close": a small database where it differs

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class GradeResult:
    verdict: str                              # correct | wrong_columns | wrong_result | wrong_in_general | invalid_expression
    message: str
    method: Optional[str] = None              # proof | tested | sample
    expected_columns: List[str] = field(default_factory=list)
    student_columns: List[str] = field(default_factory=list)
    databases_checked: int = 0
    missing_count: int = 0
    extra_count: int = 0
    extra_rows: List[list] = field(default_factory=list)
    counterexample: Optional[dict] = None
    steps: List[StepFeedback] = field(default_factory=list)
    error: Optional[dict] = None
    elapsed_ms: float = 0.0

    @property
    def correct(self) -> bool:
        return self.verdict == "correct"

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["steps"] = [s.to_dict() for s in self.steps]
        return d


@dataclass
class _Run:
    """One answer evaluated on one database: final result plus every statement's result."""
    columns: List[str]
    rows: List[tuple]
    steps: List[Tuple[Optional[str], Optional[int], Rel]]


def _run(program: ast.Program, db: Database, options: EvalOptions) -> _Run:
    r = evaluate(program, db, trace=False, options=options)
    return _Run(r.columns, r.rows, r.step_relations)


class PreparedQuestion:
    """Everything grading needs that doesn't depend on the student. Build once per question."""

    def __init__(self, schema_sql: str, model_answer: str, data_sql: str = "", *,
                 options: EvalOptions = EvalOptions(), bag: bool = False,
                 checkpoints: Optional[Sequence[Checkpoint]] = None,
                 suite: Optional[TestSuite] = None, suite_json: Optional[dict] = None,
                 gen_config: GenConfig = GenConfig(), suite_config: Optional[SuiteConfig] = None):
        self.options = options
        self.bag = bag
        self.schema = Database.from_sql(schema_sql)
        self.sample = Database.from_sql(schema_sql, data_sql) if data_sql and data_sql.strip() else None
        self.names = self.schema.names()
        self.model = parse(model_answer, self.names)
        empty_run = _run(self.model, self.schema, options)      # raises RAError for a broken model answer
        self.columns = empty_run.columns
        self.seed = question_seed(schema_sql, model_answer)
        self.gen_config = gen_config
        self.checkpoints = list(checkpoints) if checkpoints is not None else self._default_checkpoints()
        if suite is None and suite_json is not None:
            suite = TestSuite.from_json(suite_json, self.schema)
        if suite is None:
            suite = build_suite(self.schema, self.model,
                                suite_config or SuiteConfig(seed=self.seed, bag=bag, gen=gen_config), options)
        self.suite = suite
        self.model_runs = [_run(self.model, db, options) for db in suite.databases]
        self.sample_run = _run(self.model, self.sample, options) if self.sample else None
        self._model_ucq = None
        if not bag:
            try:
                self._model_ucq = to_ucq(self.model, self.schema)
            except (NotConjunctive, RAError):
                self._model_ucq = None
        self._hint_constants = _constant_set([self.model])

    def _default_checkpoints(self) -> List[Checkpoint]:
        """Every named step of the model answer, then the final answer. Labels name the
        step only: students see them, so they must never show the model's expression.
        Staff can give each checkpoint a description instead (e.g. "the CE courses")."""
        out = []
        for s in self.model.statements[:-1]:
            out.append(Checkpoint(s.name, f"step {s.name} of the model solution"))
        out.append(Checkpoint(None, "the final answer"))
        return out

    def checkpoint_index(self, cp: Checkpoint) -> int:
        """Which statement of the model answer a checkpoint refers to."""
        if cp.statement is None:
            return len(self.model.statements) - 1
        for i, s in enumerate(self.model.statements):
            if s.name and s.name.casefold() == cp.statement.casefold():
                return i
        raise ValueError(f"The model answer has no step called {cp.statement}.")

    def _checkpoint_rel(self, run: _Run, cp: Checkpoint) -> Rel:
        return run.steps[self.checkpoint_index(cp)][2]

    # ── grading ───────────────────────────────────────────────────────────────
    def grade(self, answer: str, *, with_steps: bool = True) -> GradeResult:
        started = time.perf_counter()
        result = self._grade(answer, with_steps)
        result.elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        return result

    def _grade(self, answer: str, with_steps: bool) -> GradeResult:
        expected = list(self.columns)
        try:
            student = parse(answer, self.names)
            empty_run = _run(student, self.schema, self.options)
        except RAError as e:
            return GradeResult("invalid_expression", e.message, expected_columns=expected, error=e.to_dict())

        # Run on every test database once; the steps feedback and the verdict share it.
        dbs = list(self.suite.databases)
        model_runs = list(self.model_runs)
        for db in self._extra_databases(student):
            try:
                model_runs.append(_run(self.model, db, self.options))
                dbs.append(db)
            except RAError:
                continue
        student_runs: List[_Run] = []
        for db in dbs:
            try:
                student_runs.append(_run(student, db, self.options))
            except RAError as e:
                return GradeResult("invalid_expression", e.message, expected_columns=expected,
                                   student_columns=empty_run.columns, error=e.to_dict())

        steps = self._steps(student, student_runs, model_runs, dbs) if with_steps else []
        base = dict(expected_columns=expected, student_columns=empty_run.columns, steps=steps)

        if not same_columns(expected, empty_run.columns):
            return GradeResult("wrong_columns",
                               f"Your answer has the attributes ({', '.join(empty_run.columns) or 'none'}), "
                               f"but the question asks for ({', '.join(expected)}).", **base)

        if self.sample is not None:
            try:
                srun = _run(student, self.sample, self.options)
            except RAError as e:
                return GradeResult("invalid_expression", e.message, error=e.to_dict(), **base)
            cmp = compare(self.sample_run.columns, self.sample_run.rows, srun.columns, srun.rows, bag=self.bag)
            if not cmp.equal:
                return GradeResult("wrong_result",
                                   f"On the question's data your answer has {len(cmp.missing)} missing and "
                                   f"{len(cmp.extra)} extra tuple(s).", method="sample",
                                   missing_count=len(cmp.missing), extra_count=len(cmp.extra),
                                   extra_rows=[list(r) for r in cmp.extra[:20]], **base)

        proof = self._try_proof(student)
        if proof is not None and proof.equivalent:
            return GradeResult("correct", "Correct: your answer is equivalent to the model answer on every "
                               "possible database (proved, not just tested).", method="proof",
                               databases_checked=len(dbs), **base)
        if proof is not None:
            case = self._counterexample(student, proof.counterexample, pretty=True)
            return GradeResult("wrong_in_general", self._general_message(), method="proof",
                               counterexample=case, databases_checked=len(dbs), **base)

        for db, m, s in zip(dbs, model_runs, student_runs):
            if not equal(m.columns, m.rows, s.columns, s.rows, bag=self.bag):
                case = self._counterexample(student, db)
                return GradeResult("wrong_in_general", self._general_message(), method="tested",
                                   counterexample=case, databases_checked=len(dbs), **base)
        return GradeResult("correct", f"Correct: your answer gives the same result as the model answer on all "
                           f"{len(dbs)} test databases.", method="tested", databases_checked=len(dbs), **base)

    def _general_message(self) -> str:
        if self.sample is not None:
            return ("Your answer gives the right result on the question's data, but not in general. "
                    "Here is a small database where it gives a different result from the model answer.")
        return "Here is a small database where your answer gives a different result from the model answer."

    def _try_proof(self, student: ast.Program):
        if self._model_ucq is None:
            return None
        try:
            return prove(self.model, student, self.schema, self.options)
        except (NotConjunctive, RAError):
            return None

    def _extra_databases(self, student: ast.Program) -> List[Database]:
        """Databases built around constants only the student used (e.g. a hard-coded GPA)."""
        new = _constant_set([student]) - self._hint_constants
        if not new:
            return []
        rng = random.Random(question_seed(str(self.seed), repr(sorted(new, key=repr))))
        gen = Generator(self.schema, [self.model, student], self.gen_config)
        try:
            return [gen.generate(rng) for _ in range(EXTRA_DATABASES)]
        finally:
            gen.close()

    def _differs(self, student: ast.Program):
        def check(db: Database) -> bool:
            try:
                m = _run(self.model, db, self.options)
                s = _run(student, db, self.options)
            except RAError:
                return False
            return not equal(m.columns, m.rows, s.columns, s.rows, bag=self.bag)
        return check

    def _counterexample(self, student: ast.Program, db: Database, pretty: bool = False) -> dict:
        differs = self._differs(student)
        if pretty:
            db = prettify(db, differs, avoid=self._hint_constants | _constant_set([student]))
        small = shrink(db, differs)
        m = _run(self.model, small, self.options)
        s = _run(student, small, self.options)
        cmp = compare(m.columns, m.rows, s.columns, s.rows, bag=self.bag)
        return {"tables": describe(small),
                "expected": {"columns": m.columns, "rows": [list(r) for r in m.rows]},
                "student": {"columns": s.columns, "rows": [list(r) for r in s.rows]},
                "missing": [list(r) for r in cmp.missing], "extra": [list(r) for r in cmp.extra]}

    # ── per-step feedback ─────────────────────────────────────────────────────
    def _steps(self, student: ast.Program, student_runs: List[_Run], model_runs: List[_Run],
               dbs: List[Database]) -> List[StepFeedback]:
        out: List[StepFeedback] = []
        close_cases = 0
        student_shapes = _shapes(student)
        model_shapes = _shapes(self.model)
        for k, stmt in enumerate(student.statements):
            s_rels = [run.steps[k][2] for run in student_runs]
            columns = s_rels[0].labels if s_rels else []
            fb = StepFeedback(stmt.name, stmt.pos.line, expr_to_text(stmt.expr), columns, "none")
            close_at = None
            for cp in self.checkpoints:
                m_rels = [self._checkpoint_rel(run, cp) for run in model_runs]
                if _same_everywhere(m_rels, s_rels, self.bag):
                    fb.status, fb.checkpoint = "match", cp.label
                    break
                if _same_everywhere_renamed(m_rels, s_rels, self.bag):
                    fb.status, fb.checkpoint, fb.renamed = "match", cp.label, True
                    break
                cp_shape = model_shapes[self.checkpoint_index(cp)]
                if fb.status == "none" and same_columns(m_rels[0].labels, columns) \
                        and student_shapes[k] == cp_shape:
                    fb.status, fb.checkpoint = "close", cp.label
                    close_at = (cp, next(i for i, (m, s) in enumerate(zip(m_rels, s_rels))
                                         if not equal(m.labels, m.rows, s.labels, s.rows, bag=self.bag)))
            if fb.status == "close" and close_at and close_cases < MAX_CLOSE_CASES:
                close_cases += 1
                fb.case = self._step_case(student, k, close_at[0], dbs[close_at[1]])
            out.append(fb)
        return out

    def _step_case(self, student: ast.Program, k: int, cp: Checkpoint, db: Database) -> dict:
        def differs(d: Database) -> bool:
            try:
                m = self._checkpoint_rel(_run(self.model, d, self.options), cp)
                s = _run(student, d, self.options).steps[k][2]
            except RAError:
                return False
            return not equal(m.labels, m.rows, s.labels, s.rows, bag=self.bag)
        small = shrink(db, differs)
        m = self._checkpoint_rel(_run(self.model, small, self.options), cp)
        s = _run(student, small, self.options).steps[k][2]
        return {"tables": describe(small),
                "expected": {"columns": m.labels, "rows": [list(r) for r in m.rows]},
                "student": {"columns": s.labels, "rows": [list(r) for r in s.rows]}}


def _same_everywhere(model: Sequence[Rel], student: Sequence[Rel], bag: bool) -> bool:
    return all(equal(m.labels, m.rows, s.labels, s.rows, bag=bag) for m, s in zip(model, student))


def _same_everywhere_renamed(model: Sequence[Rel], student: Sequence[Rel], bag: bool) -> bool:
    """Same tuples with the student's attributes in some order, whatever they are called."""
    if not model or not student:
        return False
    arity = len(model[0].attrs)
    if arity != len(student[0].attrs) or arity > 5 or same_columns(model[0].labels, student[0].labels):
        return False
    for perm in itertools.permutations(range(arity)):
        ok = True
        for m, s in zip(model, student):
            got = [tuple(r[i] for i in perm) for r in s.rows]
            if not equal(m.labels, m.rows, m.labels, got, bag=bag):
                ok = False
                break
        if ok:
            return True
    return False


_JOINS = ("product", "theta_join", "natural_join")


def _shapes(program: ast.Program) -> List[str]:
    """Each statement's shape: its operators and base relations, with earlier steps
    written out in full (so step names don't matter) and conditions, attribute lists and
    constants left out. Rename and δ don't change the shape; × and the joins count as one."""
    defined: Dict[str, str] = {}
    out = []

    def shape(e) -> str:
        if isinstance(e, ast.Relation):
            return defined.get(e.name.casefold(), e.name.upper())
        if isinstance(e, (ast.Rename, ast.Distinct)):
            return shape(e.child)
        if isinstance(e, ast.Select):
            return f"σ({shape(e.child)})"
        if isinstance(e, ast.Project):
            return f"Π({shape(e.child)})"
        if isinstance(e, ast.Group):
            return f"γ({shape(e.child)})"
        op = "⋈" if e.op in _JOINS else e.op
        return f"{op}({shape(e.left)},{shape(e.right)})"

    for s in program.statements:
        text = shape(s.expr)
        out.append(text)
        if s.name:
            defined[s.name.casefold()] = text
    return out


def _constant_set(programs: Sequence[ast.Program]) -> set:
    hints = collect_hints(programs)
    values = {v for consts in hints.constants.values() for _op, v in consts}
    values |= {v for _op, v in hints.loose_constants}
    return {norm_row((v,))[0] for v in values}
