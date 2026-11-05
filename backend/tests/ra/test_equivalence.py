"""The Z3 prover (core/ra/logic.py, core/ra/equivalence.py): equivalence on every valid database."""
import pytest

from app.core.ra import Database, parse
from app.core.ra import equivalence
from app.core.ra.equivalence import differ, prove, stored, valid
from app.core.ra.evaluator import EvalOptions
from app.core.ra.grader import PreparedQuestion
from app.core.ra.suite import TestSuite
from app.services.ra.tutorial_5_5 import QUESTIONS

UNI = """
CREATE TABLE Course (cid INTEGER PRIMARY KEY, title TEXT NOT NULL);
CREATE TABLE Student (sid INTEGER PRIMARY KEY, name TEXT NOT NULL, gpa REAL);
CREATE TABLE Enrolled (sid INTEGER NOT NULL REFERENCES Student(sid), cid INTEGER NOT NULL REFERENCES Course(cid),
                       PRIMARY KEY (sid, cid));
"""
# The same tables without keys or foreign keys.
LOOSE = """
CREATE TABLE Course (cid INTEGER, title TEXT);
CREATE TABLE Student (sid INTEGER, name TEXT, gpa REAL);
CREATE TABLE Enrolled (sid INTEGER, cid INTEGER);
"""
NUMS = "CREATE TABLE R (a INTEGER PRIMARY KEY, b INTEGER, c REAL);"
BAGS = "CREATE TABLE R (a INTEGER, b INTEGER);"
ONE = "CREATE TABLE R (A INTEGER);"


def check(schema_sql: str, a: str, b: str, **kw):
    db = Database.from_sql(schema_sql)
    pa, pb = parse(a, db.names()), parse(b, db.names())
    p = prove(pa, pb, db, **kw)
    if p.status == "different":
        # Never on the solver's word: a valid database where the real evaluator differs.
        assert valid(p.counterexample)
        assert differ(pa, pb, p.counterexample, kw.get("options", EvalOptions()), kw.get("bag", False))
    return p


# ── keys and foreign keys ────────────────────────────────────────────────────
def test_a_join_a_foreign_key_makes_redundant_is_proved_equivalent():
    assert check(UNI, "Π sid (Enrolled)", "Π sid (Enrolled ⋈ Course)").status == "equivalent"
    assert check(UNI, "Π sid (Enrolled)", "Π Enrolled.sid (σ Enrolled.sid = Student.sid (Enrolled × Student))"
                 ).status == "equivalent"
    # Without the foreign key it is wrong: an enrolment in a course that isn't listed.
    p = check(LOOSE, "Π sid (Enrolled)", "Π sid (Enrolled ⋈ Course)")
    assert p.status == "different"
    assert p.counterexample.lookup("Course").rows == []


def test_the_counterexample_obeys_the_schema():
    p = check(UNI, "Π sid (Enrolled)", "Π sid (Student)")
    assert p.status == "different"
    tables = {t.name: t.rows for t in p.counterexample.tables}
    assert tables["Student"] and not tables["Enrolled"]          # a student with no enrolment
    assert all(v is not None for rows in tables.values() for r in rows for v in r)


def test_a_primary_key_is_used():
    # Two tuples with the same key and different names can't exist.
    clash = "Π S1.sid (σ S1.sid = S2.sid AND S1.name <> S2.name (ρ S1 Student × ρ S2 Student))"
    nothing = "Π sid (σ sid <> sid (Student))"
    assert check(UNI, nothing, clash).status == "equivalent"
    assert check(LOOSE, nothing, clash).status == "different"


def test_an_outer_join_on_a_foreign_key_is_an_inner_join():
    assert check(UNI, "Enrolled ⋈ Course", "Enrolled ⟕ Course").status == "equivalent"
    p = check(LOOSE, "Enrolled ⋈ Course", "Enrolled ⟕ Course")
    assert p.status == "different"


def test_outer_join_nulls_follow_three_valued_logic():
    # A condition on the padded side drops the NULL tuples, so ⟕ then σ is ⋈ then σ.
    assert check(LOOSE, "σ title = 'DB' (Enrolled ⋈ Course)", "σ title = 'DB' (Enrolled ⟕ Course)"
                 ).status == "equivalent"
    # NOT (title = 'DB') is unknown on the padded NULL too, so it doesn't keep them either.
    assert check(LOOSE, "σ title <> 'DB' (Enrolled ⋈ Course)", "σ NOT (title = 'DB') (Enrolled ⟕ Course)"
                 ).status == "equivalent"


# ── comparisons, −, ÷ ─────────────────────────────────────────────────────────
def test_comparisons_respect_the_attribute_type():
    assert check(NUMS, "σ b < 50 (R)", "σ b <= 49 (R)").status == "equivalent"           # whole numbers
    p = check(NUMS, "Π a (σ c < 50 (R))", "Π a (σ c <= 49 (R))")                          # REAL: 49.5
    assert p.status == "different"
    assert 49 < p.counterexample.lookup("R").rows[0][2] < 50
    assert check(NUMS, "σ b > 3 OR b < 1 (R)", "R − σ b >= 1 AND b <= 3 (R)").status == "equivalent"
    assert check(NUMS, "σ NOT (b = 3) (R)", "σ b <> 3 (R)").status == "equivalent"


def test_difference_and_division():
    q = next(q for q in QUESTIONS if q["title"].startswith("Tutorial 5.5 Q1(iv)"))
    double_difference = ("R1 := π Dname, Cno σ Dname = 'Civil Engineering' COURSE\nR2 := π Sid, Dname, Cno ENROLL\n"
                         "R3 := π Sid R2\nR4 := π Sid ((R3 × R1) − R2)\nR5 := R3 − R4\n"
                         "Answer := π Sid, Sname, GPA (R5 ⋈ STUDENT)")
    assert check(q["schema_sql"], q["model_answer"], double_difference).status == "equivalent"
    any_course = ("R1 := π Dname, Cno σ Dname = 'Civil Engineering' COURSE\n"
                  "Answer := π Sid, Sname, GPA (STUDENT ⋈ π Sid (ENROLL ⋈ R1))")
    assert check(q["schema_sql"], q["model_answer"], any_course).status in ("different", "unknown")


@pytest.mark.parametrize("q", [q for q in QUESTIONS if "parts" not in q], ids=lambda q: q["title"][:30])
def test_every_tutorial_model_answer_is_proved_equal_to_itself(q):
    assert check(q["schema_sql"], q["model_answer"], q["model_answer"]).status == "equivalent"


# ── aggregates ────────────────────────────────────────────────────────────────
def test_min_and_max_are_proved():
    assert check(NUMS, "γ MAX(b) → m (R)", "γ MAX(b) → m (σ b = b (R))").status == "equivalent"
    # γ over an empty relation gives one tuple (NULL); the "max without γ" answer gives none.
    p = check(ONE, "γ MAX(A) → A (R)", "S := R\nR1 := σ R.A < S.A (R × S)\nR − π R.A (R1)")
    assert p.status == "different" and p.counterexample.lookup("R").rows == []
    assert check(NUMS, "γ MIN(b) → m (R)", "γ MAX(b) → m (R)").status == "different"


def test_count_is_shared_only_when_the_inputs_are_proved_the_same():
    same = check(NUMS, "γ COUNT(*) → n (σ b < 5 (R))", "γ COUNT(*) → n (σ b <= 4 (R))")
    assert same.status == "equivalent"
    assert check(NUMS, "γ b, COUNT(a) → n (R)", "γ b, COUNT(a) → n (σ a = a (R))").status == "equivalent"
    # Different inputs: no claim either way unless the logic shows a difference.
    assert check(NUMS, "γ COUNT(*) → n (σ b < 5 (R))", "γ COUNT(*) → n (σ b < 6 (R))").status != "equivalent"
    # Without a key, R may repeat tuples after Π, so equal sets don't give equal counts.
    assert check(BAGS, "γ COUNT(*) → n (Π a (R))", "γ COUNT(*) → n (Π a (σ a = a (R)))").status != "equivalent"


def test_bag_comparison_needs_answers_without_duplicates():
    assert check(NUMS, "Π b (R)", "Π b (σ b = b (R))", bag=True).status == "unknown"
    assert check(NUMS, "σ b > 1 (R)", "σ 1 < b (R)", bag=True).status == "equivalent"


# ── the procedure itself ─────────────────────────────────────────────────────
def test_proofs_are_deterministic():
    a = check(NUMS, "γ COUNT(*) → n (σ b < 5 (R))", "γ COUNT(*) → n (σ b <= 4 (R))")
    b = check(NUMS, "γ COUNT(*) → n (σ b < 5 (R))", "γ COUNT(*) → n (σ b <= 4 (R))")
    assert (a.status, a.how, a.work) == (b.status, b.how, b.work)


def test_parts_proved_equal_are_replaced_when_the_whole_is_undecided(monkeypatch):
    monkeypatch.setattr(equivalence, "MAIN_SHARE", 0.000001)          # the first attempt can't finish
    p = check(UNI, "Π name (Student ⋈ Enrolled) − Π name (σ gpa < 2 (Student))",
              "Π name (Enrolled ⋈ Student) − Π name (σ 2 > gpa (Student))")
    assert p.status == "equivalent" and p.how == "by_parts"


def test_the_work_is_bounded(monkeypatch):
    monkeypatch.setattr(equivalence, "BUDGET", 1000)
    p = check(UNI, "Π sid (Enrolled)", "Π sid (Enrolled ⋈ Course)")
    assert p.status == "unknown" and p.work <= 1000 + 5000


def test_anything_the_logic_cannot_express_is_left_to_testing():
    p = check(NUMS, "Π a, b → x (R)", "Π a, a * a → x (R)")
    assert p.status in ("unknown", "different")       # nonlinear arithmetic: never a false proof
    assert check(NUMS, "Π a, b + 1 → x (R)", "Π a, 1 + b → x (R)").status == "equivalent"


def test_stored_refuses_nulls_and_broken_keys():
    db = Database.from_sql(UNI)
    assert stored(db.with_rows({"Student": [(1, "Ann", None)]})) is None
    assert stored(db.with_rows({"Enrolled": [(1, 2)]})) is None                          # no such student
    assert stored(db.with_rows({"Student": [(1, "Ann", 3.0), (1, "Bob", 3.5)]})) is None   # same key
    ok = stored(db.with_rows({"Student": [(1, "Ann", 3.0)], "Course": [(2, "DB")], "Enrolled": [(1, 2)]}))
    assert ok is not None and ok.lookup("Enrolled").rows == [(1, 2)]


# ── in the grader ─────────────────────────────────────────────────────────────
def test_the_grader_proves_what_the_tests_accept():
    q = PreparedQuestion(UNI, "Π sid (Enrolled)")
    r = q.grade("Π sid (Enrolled ⋈ Course)")
    assert r.verdict == "correct" and r.method == "proof"
    # Students get the same message whether it was proved or only tested.
    assert r.message == "Correct: your answer gives the same result as the model answer."


def test_the_grader_finds_what_weak_tests_miss():
    """With only the empty database to test on, the wrong answer passes every test; the
    proof still finds a small valid database where it differs, with readable values."""
    schema = Database.from_sql(UNI)
    # (No NULLs in stored tables, so gpa > 2 OR gpa <= 2 keeps every student.)
    q = PreparedQuestion(UNI, "Π name (σ gpa > 2 OR gpa <= 2 (Student))", suite=TestSuite([schema.with_rows({})]))
    assert q.grade("Π name (Student)").method == "proof"
    r = q.grade("Π name (σ gpa > 2 (Student))")
    assert r.verdict == "wrong_in_general" and r.method == "proof"
    rows = r.counterexample["tables"]["Student"]["rows"]
    assert len(rows) == 1 and rows[0][2] <= 2
    assert rows[0][1] == "name_1"                     # not a solver-made string such as "!0!"


def test_a_shrunk_counterexample_keeps_its_foreign_keys():
    q = PreparedQuestion(UNI, "Π cid (Enrolled)")
    r = q.grade("Π cid (Course)")
    assert r.verdict == "wrong_in_general"
    tables = r.counterexample["tables"]
    assert "Course" in tables and "Enrolled" not in tables       # a course nobody took, nothing else
