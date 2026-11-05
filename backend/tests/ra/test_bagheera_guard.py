"""Bagheera's leak guard: replies that solve a part or a model step are caught."""
from app.core.ra.grader import PreparedQuestion
from app.services.ra.bagheera_guard import candidates, leaks
from app.services.ra.tutorial_5_5 import QUESTIONS

Q1_IV = next(q for q in QUESTIONS if q["title"].startswith("Tutorial 5.5 Q1(iv)"))
PQ = PreparedQuestion(Q1_IV["schema_sql"], Q1_IV["model_answer"])


def test_expressions_are_found_in_code_inline_and_prose():
    reply = ("Try this:\n```\nπ Sid (ENROLL)\n```\nor `σ GPA > 3 (STUDENT)`. "
             "You could also write π Sname (STUDENT) to list the names.")
    found = candidates(reply, PQ.names)
    assert "π Sid (ENROLL)" in found and "σ GPA > 3 (STUDENT)" in found
    assert any(c.startswith("π Sname (STUDENT)") for c in found)


def test_the_model_answer_and_its_steps_leak():
    assert leaks(f"Here you go:\n```\n{Q1_IV['model_answer']}\n```", [PQ])
    # A model step on its own (R1: the Civil Engineering courses) is a leak too.
    assert leaks("First get `π Dname, Cno (σ Dname = 'Civil Engineering' COURSE)`.", [PQ])
    # The same answer written another way, over two prose lines, is still caught.
    two_lines = ("R1 := π Dname, Cno σ Dname = 'Civil Engineering' COURSE\n"
                 "R2 := π Sid, Sname, GPA ((π Sid, Dname, Cno ENROLL ÷ R1) ⋈ STUDENT)")
    assert leaks(two_lines, [PQ])


def test_hints_and_small_examples_do_not_leak():
    assert not leaks("Think about ÷: which students are paired with *every* course? On R(A, B) and S(B), "
                     "`R ÷ S` keeps the A values paired with all of S.", [PQ])
    assert not leaks("Your `π Sid (ENROLL)` is close: it lists everyone who took any course.", [PQ])
    assert not leaks("No RA here at all, just words.", [PQ])
