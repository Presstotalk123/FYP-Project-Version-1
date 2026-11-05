"""The three question types (core/ra/answer_format.py) and multi-step marking (step_marking.py)."""
import random

import pytest

from app.core.ra import Database, RAError, evaluate, parse
from app.core.ra.answer_format import (Step, has_steps, join, single_expression, split, steps_checkpoints,
                                       steps_program)
from app.core.ra.compare import equal
from app.core.ra.generator import GenConfig, Generator
from app.core.ra.grader import PreparedQuestion
from app.core.ra.step_marking import mark
from app.services.ra.tutorial_5_5 import QUESTIONS, UNIVERSITY

NAMES = Database.from_sql(UNIVERSITY).names()

STEPS = [Step("R1", "the Civil Engineering courses", 3, "π Dname, Cno (σ Dname = 'Civil Engineering' COURSE)"),
         Step("R2", "who took which course", 3, "π Sid, Dname, Cno ENROLL"),
         Step("R3", "students who took all of them", 2, "R2 ÷ R1"),
         Step(None, "their ids, names and GPAs", 2, "π Sid, Sname, GPA (R3 ⋈ STUDENT)")]
MODEL = [s.model_answer for s in STEPS]


@pytest.fixture(scope="module")
def prepared():
    return PreparedQuestion(UNIVERSITY, steps_program(STEPS))


# ── one expression ↔ steps ───────────────────────────────────────────────────
@pytest.mark.parametrize("q", [q for q in QUESTIONS if "model_answer" in q], ids=lambda q: q["title"][:30])
def test_joining_the_steps_keeps_the_meaning(q):
    """Every tutorial model answer, joined into one expression, gives the same result on
    generated databases (including R1.MinGPA, which keeps its name as ρ R1 (…))."""
    schema = Database.from_sql(q["schema_sql"])
    one = join(q["model_answer"], schema.names())
    single_expression(one, schema.names())                       # really one expression
    a, b = parse(q["model_answer"], schema.names()), parse(one, schema.names())
    gen = Generator(schema, [a], GenConfig())
    rng = random.Random(7)
    try:
        for _ in range(25):
            db = gen.generate(rng)
            ra, rb = evaluate(a, db), evaluate(b, db)
            assert equal(ra.columns, ra.rows, rb.columns, rb.rows)
    finally:
        gen.close()


def test_join_keeps_a_name_used_as_a_qualifier():
    one = join("R1 := γ MIN(GPA)→MinGPA (STUDENT)\nAnswer := π Sname (STUDENT ⋈ STUDENT.GPA=R1.MinGPA R1)", NAMES)
    assert "ρ R1" in one and ":=" not in one


def test_a_single_expression_is_left_as_written():
    assert join("π Sname STUDENT", NAMES) == "π Sname STUDENT"


def test_split_makes_one_step_per_statement_with_the_checkpoint_labels_as_prompts():
    steps = split("R1 := σ Numphds < 50 (DEPT)\nAnswer := π Pname (PROF ⋈ R1)", NAMES,
                  [{"statement": "R1", "label": "small departments"}, {"statement": None, "label": "the final answer"}], 5)
    assert [(s.name, s.prompt, s.marks) for s in steps] == [("R1", "small departments", 2), (None, "", 3)]
    assert steps[1].model_answer == "Π Pname (PROF ⋈ R1)"


def test_a_single_expression_becomes_one_step():
    [step] = split("π Sname STUDENT", NAMES, None, 4)
    assert step.name is None and step.marks == 4


def test_steps_program_and_checkpoints():
    assert steps_program(STEPS).splitlines()[0] == "R1 := π Dname, Cno (σ Dname = 'Civil Engineering' COURSE);"
    assert [c["statement"] for c in steps_checkpoints(STEPS)] == ["R1", "R2", "R3", None]
    assert steps_checkpoints(STEPS)[0]["label"] == "the Civil Engineering courses"


@pytest.mark.parametrize("text, steps", [("π Sname STUDENT", False), ("R1 := STUDENT\nπ Sname R1", True),
                                         ("  Temp ← STUDENT\nTemp", True)])
def test_has_steps(text, steps):
    assert has_steps(text) is steps


def test_single_expression_rejects_steps():
    with pytest.raises(RAError) as e:
        single_expression("R1 := STUDENT\nπ Sname R1", NAMES)
    assert e.value.code == "RA012"


# ── marking ──────────────────────────────────────────────────────────────────
def _marks(m):
    return [(s.status, s.earned) for s in m.steps]


def test_the_model_answer_earns_everything(prepared):
    m = mark(prepared, STEPS, MODEL)
    assert m.grade.correct and m.earned == m.total == 10 and {s.status for s in m.steps} == {"full"}


def test_a_correct_final_answer_earns_everything_whatever_the_steps(prepared):
    """Empty steps, the whole answer in the last box: still full marks."""
    final = "π Sid, Sname, GPA ((π Sid, Dname, Cno ENROLL ÷ π Dname, Cno (σ Dname = 'Civil Engineering' COURSE)) ⋈ STUDENT)"
    m = mark(prepared, STEPS, ["", "", "", final])
    assert m.grade.correct and m.earned == 10
    assert [b.status for b in m.boxes] == ["empty", "empty", "empty", "ok"]


def test_steps_in_another_order_still_score(prepared):
    """R1 and R2 swapped (and the final answer wrong): each model step is found in the other box."""
    m = mark(prepared, STEPS, ["π Sid, Dname, Cno ENROLL", "π Dname, Cno (σ Dname = 'Civil Engineering' COURSE)",
                               "R1 ÷ R2", "π Sid, Sname (R3 ⋈ STUDENT)"])
    assert not m.grade.correct
    assert _marks(m) == [("reached", 3), ("reached", 3), ("reached", 2), ("missed", 0)]
    assert [s.credited_by for s in m.steps[:3]] == [1, 0, 2]


def test_carry_forward_after_a_wrong_first_step(prepared):
    """R1 picks the wrong department: R2 is right on its own, R3 and the final answer are
    right given the model's R1, so only R1's 3 marks are lost."""
    wrong = ["π Dname, Cno (σ Dname = 'Computer Science' COURSE)"] + MODEL[1:]
    m = mark(prepared, STEPS, wrong)
    assert not m.grade.correct
    assert _marks(m) == [("missed", 0), ("reached", 3), ("carried", 2), ("carried", 2)]
    assert m.earned == 7


def test_wrong_final_attributes_keep_the_step_marks(prepared):
    m = mark(prepared, STEPS, MODEL[:3] + ["π Sid, Sname (R3 ⋈ STUDENT)"])
    assert m.grade.verdict == "wrong_columns" and m.earned == 8 and m.steps[3].status == "missed"


def test_box_errors_are_reported_where_they_are(prepared):
    m = mark(prepared, STEPS, ["σ Foo = 1 COURSE", "R1 ⋈ ENROLL", "R1 := R2", ""])
    assert [b.status for b in m.boxes] == ["error", "error", "error", "empty"]
    assert "Foo" in m.boxes[0].error["message"]
    assert "your step R1 has an error" in m.boxes[1].error["message"]
    assert "one expression" in m.boxes[2].error["message"]
    assert m.grade.verdict == "invalid_expression" and m.earned == 0


def test_a_step_can_only_use_earlier_steps(prepared):
    m = mark(prepared, STEPS, ["R2", "ENROLL", "", ""])
    assert m.boxes[0].status == "error" and "R2 comes later" in m.boxes[0].error["message"]


def test_marking_is_deterministic(prepared):
    wrong = ["π Dname, Cno (σ Dname = 'Computer Science' COURSE)"] + MODEL[1:]
    assert mark(prepared, STEPS, wrong).to_dict() == mark(prepared, STEPS, wrong).to_dict()
