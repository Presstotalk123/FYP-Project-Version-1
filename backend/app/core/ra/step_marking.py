"""Marking a multi-step answer: one box per step of the professor's (answer_format.py).

The student fills in one box per step; box k is named like step k (R1, R2, …, names the
professor chose), may use the names of earlier steps, and holds one expression. The last
box is the final answer. Marks (deterministic, no judgement involved):

  1. The final answer is graded exactly like any answer (grader.py), with the student's
     steps as its R1 := … lines. Correct → every step's marks, whatever the steps look
     like: a different, valid method is never punished.
  2. Otherwise each step of the model answer earns its marks when one of the student's
     boxes computes the same thing, i.e. the same tuples on every test database (and the
     question's data). Any box counts, so steps done in another order still score; each
     box earns at most one step.
  3. Carry-forward: a box that is wrong only because an earlier step it uses is wrong is
     run again with the model's earlier steps in place of the student's. If it then
     gives the model's step, it earns that step ("right, given your step R1"). This is
     also how the final step can earn its own share when the answer as a whole is wrong.
     The final step is never credited any other way: whether the answer itself is
     right is the grader's call (it also tests constants only the student used).

A box can be empty (it earns nothing) or have an error (shown at that box, earns
nothing; later boxes that use it get "uses R1, which has an error").
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from app.core.ra import ast
from app.core.ra import errors as E
from app.core.ra.answer_format import Step, single_expression
from app.core.ra.compare import equal
from app.core.ra.errors import RAError
from app.core.ra.evaluator import EvalOptions, Rel, evaluate
from app.core.ra.grader import GradeResult, PreparedQuestion, _same_everywhere_renamed
from app.core.ra.printer import program_to_text
from app.core.ra.schema import Database


@dataclass
class BoxResult:
    status: str                         # empty | error | ok
    error: Optional[dict] = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class StepMark:
    index: int
    name: Optional[str]
    prompt: str
    marks: int
    earned: int = 0
    # full (the final answer is correct) | reached (a box computes it) |
    # carried (a box computes it given the model's earlier steps) | missed
    status: str = "missed"
    credited_by: Optional[int] = None   # the box that earned it (0-based)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class StepMarking:
    steps: List[StepMark]
    boxes: List[BoxResult]
    grade: GradeResult                  # the final answer's grade
    program: str                        # the student's boxes as one program (R1 := …), "" if none run
    statement_boxes: List[int] = field(default_factory=list)   # which box each statement of ``program`` is

    @property
    def earned(self) -> int:
        return sum(s.earned for s in self.steps)

    @property
    def total(self) -> int:
        return sum(s.marks for s in self.steps)

    def to_dict(self) -> dict:
        return {"steps": [s.to_dict() for s in self.steps], "boxes": [b.to_dict() for b in self.boxes],
                "earned": self.earned, "total": self.total, "final_correct": self.grade.correct}


def _relations(expr, out: Set[str]) -> Set[str]:
    if isinstance(expr, ast.Relation):
        out.add(expr.name.casefold())
    for child in ast.children(expr):
        _relations(child, out)
    return out


class Boxes:
    """Boxes read one by one (a student's answers, or the professor's step model answers
    when a question is saved): each must be one expression using only the schema and
    earlier steps that work."""

    def __init__(self, schema: Database, options: EvalOptions, steps: Sequence[Step], answers: Sequence[str]):
        self.results: List[BoxResult] = []
        self.statements: List[Tuple[int, ast.Statement]] = []      # (box, statement) for the boxes that work
        self.uses: Dict[int, Set[str]] = {}                        # box → the step names it uses
        step_index = {s.name.casefold(): i for i, s in enumerate(steps) if s.name}
        ok_names: Set[str] = set()
        for k, step in enumerate(steps):
            text = answers[k] if k < len(answers) else ""
            if not (text or "").strip():
                self.results.append(BoxResult("empty"))
                continue
            try:
                expr = single_expression(text, schema.names())
                used = {n for n in _relations(expr, set()) if n in step_index}
                for n in sorted(used, key=lambda n: step_index[n]):
                    label = steps[step_index[n]].name
                    if step_index[n] >= k:
                        raise RAError(E.UNKNOWN_RELATION, f"A step can only use the steps before it; "
                                      f"{label} comes {'later' if step_index[n] > k else 'here'}.")
                    if n not in ok_names:
                        state = self.results[step_index[n]].status
                        raise RAError(E.UNKNOWN_RELATION, f"This uses {label}, but your step {label} "
                                      f"{'is empty' if state == 'empty' else 'has an error'}.")
                statement = ast.Statement(step.name, expr)
                program = ast.Program([s for _k, s in self.statements] + [statement])
                evaluate(program, schema, trace=False, options=options)    # errors show here
            except RAError as e:
                self.results.append(BoxResult("error", e.to_dict()))
                continue
            self.results.append(BoxResult("ok"))
            self.statements.append((k, statement))
            self.uses[k] = used
            if step.name:
                ok_names.add(step.name.casefold())

    def program(self) -> Optional[ast.Program]:
        return ast.Program([s for _k, s in self.statements]) if self.statements else None


def _box_relations(boxes: Boxes, dbs: Sequence[Database], prepared: PreparedQuestion) -> Dict[int, List[Optional[Rel]]]:
    """Each working box's result on each database (None where it can't run)."""
    out: Dict[int, List[Optional[Rel]]] = {k: [] for k, _s in boxes.statements}
    program = boxes.program()
    for db in dbs:
        try:
            rels = [r for _n, _l, r in evaluate(program, db, trace=False, options=prepared.options).step_relations]
        except RAError:
            rels = []
            for i in range(len(boxes.statements)):              # run each box on its own
                try:
                    prefix = ast.Program([s for _k, s in boxes.statements[:i + 1]])
                    rels.append(evaluate(prefix, db, trace=False, options=prepared.options).step_relations[-1][2])
                except RAError:
                    rels.append(None)
        for (k, _s), rel in zip(boxes.statements, rels):
            out[k].append(rel)
    return out


def _same(model: Sequence[Rel], student: Sequence[Optional[Rel]], bag: bool) -> bool:
    if len(model) != len(student) or any(s is None for s in student):
        return False
    if all(equal(m.labels, m.rows, s.labels, s.rows, bag=bag) for m, s in zip(model, student)):
        return True
    return _same_everywhere_renamed(model, student, bag)


def mark(prepared: PreparedQuestion, steps: Sequence[Step], answers: Sequence[str]) -> StepMarking:
    """Mark one multi-step answer. ``prepared`` is the part's model answer built from
    ``steps`` (answer_format.steps_program), so model statement j is step j."""
    boxes = Boxes(prepared.schema, prepared.options, steps, answers)
    marks = [StepMark(i, s.name, s.prompt, s.marks) for i, s in enumerate(steps)]
    last = len(steps) - 1
    program = boxes.program()
    final_ok = boxes.results[last].status == "ok"

    if not final_ok:
        error = boxes.results[last].error
        grade = GradeResult("invalid_expression", error["message"] if error else
                            "You haven't written the final answer (the last step).",
                            expected_columns=list(prepared.columns), error=error)
    else:
        grade = prepared.grade(program_to_text(program))
    result = StepMarking(marks, boxes.results, grade, program_to_text(program) if program else "",
                         [k for k, _s in boxes.statements])
    if grade.correct:
        for m in marks:
            m.earned, m.status = m.marks, "full"
        return result
    if program is None:
        return result

    dbs = list(prepared.suite.databases)
    model_runs = list(prepared.model_runs)
    if prepared.sample is not None:
        dbs.append(prepared.sample)
        model_runs.append(prepared.sample_run)
    model_rels = [[run.steps[j][2] for run in model_runs] for j in range(len(steps))]
    student_rels = _box_relations(boxes, dbs, prepared)
    used: Set[int] = set()

    def order(j: int) -> List[int]:
        return [j] + [k for k in student_rels if k != j] if j in student_rels else list(student_rels)

    # 2. a box computes the step (any order); the final step only through 3.
    for j in range(last):
        for k in order(j):
            if k not in used and _same(model_rels[j], student_rels[k], prepared.bag):
                marks[j].earned, marks[j].status, marks[j].credited_by = marks[j].marks, "reached", k
                used.add(k)
                break

    # 3. carry-forward: the box with the model's earlier steps in place of the student's.
    model_statements = prepared.model.statements
    for j in range(len(steps)):
        if marks[j].status != "missed":
            continue
        candidates = [last] if j == last else [k for k in order(j) if k != last]
        for k in candidates:
            if k in used or k not in student_rels or not boxes.uses.get(k):
                continue
            statement = next(s for b, s in boxes.statements if b == k)
            carried = ast.Program(list(model_statements[:k]) + [ast.Statement(None, statement.expr)])
            rels: List[Optional[Rel]] = []
            for db in dbs:
                try:
                    rels.append(evaluate(carried, db, trace=False, options=prepared.options).step_relations[-1][2])
                except RAError:
                    rels.append(None)
                    break
            if _same(model_rels[j], rels, prepared.bag):
                marks[j].earned, marks[j].status, marks[j].credited_by = marks[j].marks, "carried", k
                used.add(k)
                break
    return result
