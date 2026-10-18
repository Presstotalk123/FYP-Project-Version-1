"""The grader on Tutorial 5.5 (SC2207), using the schemas only, with no question data.

For each question: the tutorial's model answer (as written on the solution slides) must
be accepted, other correct answers must be accepted, and typical wrong answers must be
rejected with a counterexample. The two cases the earlier prototype got wrong — MAX
instead of MIN (Q1 ii) and "any" instead of "all" (Q1 iv) — are here.
"""
import pytest

from app.core.ra.grader import Checkpoint, PreparedQuestion
from app.services.ra.examples import TUTORIAL_Q1, TUTORIAL_Q2

Q1 = TUTORIAL_Q1["schema_sql"]
Q2 = TUTORIAL_Q2["schema_sql"]
Q3 = """CREATE TABLE Teams (name TEXT, groupname TEXT, teamid INTEGER PRIMARY KEY);
CREATE TABLE Results ("teamid-one" INTEGER, "teamid-two" INTEGER, scoreone INTEGER, scoretwo INTEGER,
  matchdate TEXT, PRIMARY KEY ("teamid-one", "teamid-two", matchdate),
  CHECK ("teamid-one" < "teamid-two"));"""
Q4 = "CREATE TABLE R (A INTEGER);"
Q5 = "CREATE TABLE R (a INTEGER, b INTEGER); CREATE TABLE S (b INTEGER, c INTEGER);"

_cache = {}


def question(schema, model, data=""):
    key = (schema, model, data)
    if key not in _cache:
        _cache[key] = PreparedQuestion(schema, model, data)
    return _cache[key]


Q1_I = "R1 := σ Numphds < 50 (DEPT)\nAnswer := π Pname (PROF ⋈ R1)"
Q1_II = "R1 := γ MIN(GPA)→MinGPA (STUDENT)\nR2 := STUDENT ⋈ STUDENT.GPA=R1.MinGPA R1\nAnswer := π Sname (R2)"
Q1_III = ("R1 := π Dname, Cno (σ Cname=‘Database Systems’ COURSE)\nR2 := π Sid (R1 ⋈ ENROLL)\n"
          "Answer := π Sname, Dname (R2 ⋈ MAJOR ⋈ STUDENT)")
Q1_IV = ("R1 := π Dname, Cno (σ Dname = ‘Civil Engineering’ COURSE)\nR2 := π Sid, Dname, Cno ENROLL\n"
         "R3 := R2 ÷ R1\nAnswer := π Sid, Sname, GPA (R3 ⋈ STUDENT)")
Q2_I = ("π source_city ( σ destination_city = “Minneapolis” (TRAINS)) ∩ "
        "π source_city ( σ destination_city = “San Francisco” (TRAINS))")
Q2_II = "π train_num, date (DEPARTURES) - π train_num, date ( RESERVATIONS)"
Q3_I = ("R1 := π teamid-one, teamid-two (σ scoreone > scoretwo (Results))\t // team one won\n"
        "R2 := π teamid-one, teamid-two (σ scoreone < scoretwo (Results))\t // team two won\n"
        "R3 := R1 ∪ R2\t\t\t\t\t// these are all the winners\n"
        "R4 := π teamid-one, teamid-two ((Results))\t\t\t// all teams\nAnswer := R4 - R3")
Q3_II = ("R1 := ρ s1(teamid)(π teamid-one (σ scoreone >= scoretwo (Results)))\n"
         "R2 := ρ s2(teamid)(π teamid-two (σ scoreone <= scoretwo (Results)))\n"
         "temp1 := R1 ∪ R2\ntemp2 := π teamid (Teams) - temp1\nresult := π name (Teams ⋈ temp2)")
Q4_MODEL = "S := R\nR1 := σ R.A < S.A (R × S)\nAnswer := R – π R.A (R1)"
Q5_MODEL = ("Temp1 := (R × ρR1 (R) × ρR2 (R))\n"
            "Temp2 := σ R1.a > R.a AND R2.a > R1.a (Temp1)\t// Looking for 3rd value and onwards\n"
            "Answer := π a (R) – π R.a (Temp2)")

ACCEPT = [
    # (schema, model, answer, why it is correct)
    (Q1, Q1_I, Q1_I, "the model answer itself"),
    (Q1, Q1_I, "π Pname σ Numphds < 50 (PROF ⋈ DEPT)", "one expression, σ after the join"),
    (Q1, Q1_I, "π Pname (PROF ⋈ σ Numphds <= 49 DEPT)", "≤ 49 is < 50 for whole numbers"),
    (Q1, Q1_II, Q1_II, "the model answer itself"),
    (Q1, Q1_II, "temp := γ MIN(GPA) → m STUDENT\nπ Sname (STUDENT ⋈ GPA = m temp)", "other names, fewer steps"),
    (Q1, Q1_II, "R1 := STUDENT\nR2 := π STUDENT.Sid (STUDENT ⋈ STUDENT.GPA > R1.GPA R1)\n"
                "R3 := π Sid STUDENT − R2\nAnswer := π Sname (R3 ⋈ STUDENT)", "no aggregation: by difference on Sid"),
    (Q1, Q1_III, Q1_III, "the model answer itself"),
    (Q1, Q1_III, "π Sname, Dname (STUDENT ⋈ MAJOR ⋈ π Sid (ENROLL ⋈ π Dname, Cno σ Cname = 'Database Systems' COURSE))",
     "one expression, joins in another order"),
    (Q1, Q1_IV, Q1_IV, "the model answer itself"),
    (Q1, Q1_IV, "R1 := π Dname, Cno σ Dname = 'Civil Engineering' COURSE\nR2 := π Sid, Dname, Cno ENROLL\n"
                "R3 := π Sid R2\nR4 := π Sid ((R3 × R1) − R2)\nR5 := R3 − R4\n"
                "Answer := π Sid, Sname, GPA (R5 ⋈ STUDENT)", "÷ written as a double difference"),
    (Q2, Q2_I, Q2_I, "the model answer itself"),
    (Q2, Q2_I, "π source_city σ destination_city = 'Minneapolis' TRAINS ⋈ "
               "π source_city σ destination_city = 'San Francisco' TRAINS", "∩ written as a natural join"),
    (Q2, Q2_II, Q2_II, "the model answer itself"),
    (Q3, Q3_I, Q3_I, "the model answer itself"),
    (Q3, Q3_I, "π teamid-one, teamid-two Results − π teamid-one, teamid-two σ scoreone <> scoretwo Results",
     "all pairs minus pairs with a decided match"),
    (Q3, Q3_II, Q3_II, "the model answer itself"),
    (Q4, Q4_MODEL, Q4_MODEL, "the model answer itself"),
    (Q4, Q4_MODEL, "δ (R − π R.A σ R.A < T.A (R × ρ T R))", "same idea, one expression, ρ instead of :="),
    (Q5, Q5_MODEL, Q5_MODEL, "the model answer itself"),
]

REJECT = [
    (Q1, Q1_I, "π Pname (PROF ⋈ σ Numphds <= 50 DEPT)", "≤ instead of <"),
    (Q1, Q1_I, "π Pname (PROF ⋈ σ Numphds > 50 DEPT)", "the wrong direction"),
    (Q1, Q1_I, "π Pname PROF", "condition forgotten"),
    (Q1, Q1_II, Q1_II.replace("MIN", "MAX"), "MAX instead of MIN (the prototype accepted this)"),
    (Q1, Q1_II, "π Sname σ GPA = 2.4 STUDENT", "a hard-coded GPA"),
    (Q1, Q1_II, "R1 := STUDENT\nR2 := STUDENT ⋈ STUDENT.GPA > R1.GPA R1\n"
                "Answer := π Sname STUDENT − π STUDENT.Sname R2", "difference on names, which can repeat"),
    (Q1, Q1_III, Q1_III.replace("π Dname, Cno (", "π Cno ("), "course matched on Cno only"),
    (Q1, Q1_IV, "R1 := π Dname, Cno σ Dname = 'Civil Engineering' COURSE\n"
                "Answer := π Sid, Sname, GPA (STUDENT ⋈ π Sid (ENROLL ⋈ R1))", "any CE course instead of all "
                                                                              "(the prototype accepted this)"),
    (Q1, Q1_IV, "R1 := π Dname, Cno σ Dname = 'Civil Engineering' COURSE\nR2 := γ COUNT(Cno) → N R1\n"
                "R3 := γ Sid, COUNT(Cno) → M (π Sid, Dname, Cno ENROLL ⋈ R1)\nR4 := π Sid σ M = N (R3 × R2)\n"
                "Answer := π Sid, Sname, GPA (R4 ⋈ STUDENT)", "counting: two sections of one course count twice"),
    (Q2, Q2_I, Q2_I.replace("∩", "∪"), "∪ instead of ∩"),
    (Q2, Q2_II, "π train_num, date (RESERVATIONS) - π train_num, date (DEPARTURES)", "sides of − swapped"),
    (Q3, Q3_I, "π teamid-one, teamid-two σ scoreone = scoretwo Results", "some tie instead of all ties"),
    (Q4, Q4_MODEL, Q4_MODEL.replace("R.A < S.A", "R.A > S.A"), "the minimum instead of the maximum"),
    (Q5, Q5_MODEL, Q5_MODEL.replace("R1.a > R.a AND R2.a > R1.a", "R1.a >= R.a AND R2.a >= R1.a"),
     "≥ instead of >"),
]


@pytest.mark.parametrize("schema, model, answer, why", ACCEPT, ids=[a[3] for a in ACCEPT])
def test_correct_answers_are_accepted(schema, model, answer, why):
    r = question(schema, model).grade(answer)
    assert r.verdict == "correct", (why, r.message, r.counterexample)


@pytest.mark.parametrize("schema, model, answer, why", REJECT, ids=[a[3] for a in REJECT])
def test_wrong_answers_are_rejected_with_a_counterexample(schema, model, answer, why):
    r = question(schema, model).grade(answer)
    assert r.verdict == "wrong_in_general", (why, r.verdict, r.message)
    ce = r.counterexample
    assert ce and ce["missing"] or ce["extra"]
    # Small enough to read at a glance.
    assert sum(len(t["rows"]) for t in ce["tables"].values()) <= 8


def test_every_mutant_of_every_model_answer_is_caught_or_reported():
    for schema, model in {(s, m) for s, m, *_ in ACCEPT}:
        summary = question(schema, model).suite.summary()
        assert summary["mutants"] > 0
        # Survivors are listed for staff with a readable description.
        for m in summary["surviving_mutants"]:
            assert m["description"] and m["text"]


def test_conjunctive_answers_are_proved_not_just_tested():
    r = question(Q1, Q1_III).grade(
        "π Sname, Dname (STUDENT ⋈ MAJOR ⋈ π Sid (ENROLL ⋈ π Dname, Cno σ Cname = 'Database Systems' COURSE))")
    assert r.verdict == "correct" and r.method == "proof"
    wrong = question(Q1, Q1_III).grade(Q1_III.replace("π Dname, Cno (", "π Cno ("))
    assert wrong.verdict == "wrong_in_general" and wrong.method == "proof"
    # The proof's counterexample uses readable values, not ⟨v1⟩ placeholders.
    values = [v for t in wrong.counterexample["tables"].values() for row in t["rows"] for v in row]
    assert not any(isinstance(v, str) and v.startswith("⟨") for v in values)


def test_aggregation_differs_on_an_empty_relation():
    """γ MAX(A) R returns one tuple (NULL) when R is empty, as in SQL; the model answer
    returns nothing. The grader finds this from the schema alone. (Whether the course
    counts it as wrong is a question for the coordinator, like COUNT and NULL.)"""
    r = question(Q4, Q4_MODEL).grade("γ MAX(A) → A R")
    assert r.verdict == "wrong_in_general"
    assert r.counterexample["tables"] == {} and r.counterexample["extra"] == [[None]]


def test_errors_and_wrong_attributes():
    q = question(Q1, Q1_I)
    bad = q.grade("π Pname σ NumPhD < 50 (PROF ⋈ DEPT)")
    assert bad.verdict == "invalid_expression" and bad.error["code"] == "RA003" and bad.error["line"] == 1
    cols = q.grade("π Pname, Dname (PROF ⋈ σ Numphds < 50 DEPT)")
    assert cols.verdict == "wrong_columns" and cols.expected_columns == ["Pname"]


def test_question_data_is_checked_first():
    data = TUTORIAL_Q1["data_sql"]
    q = question(Q1, Q1_II, data)
    r = q.grade(Q1_II.replace("MIN", "MAX"))
    assert r.verdict == "wrong_result" and r.extra_rows == [["Ann"]] and r.missing_count == 2
    # Right on the question's data by coincidence, wrong in general.
    lucky = q.grade("π Sname σ GPA = 2.4 STUDENT")
    assert lucky.verdict == "wrong_in_general" and "not in general" in lucky.message


# ── step feedback ("Show structure") ─────────────────────────────────────────
def test_steps_match_by_content_whatever_their_names():
    r = question(Q1, Q1_IV).grade(
        "ce := π Dname, Cno σ Dname = 'Civil Engineering' COURSE\n"
        "took := π Sid, Dname, Cno ENROLL\nall := took ÷ ce\nπ Sid, Sname, GPA (all ⋈ STUDENT)")
    assert [s.status for s in r.steps] == ["match"] * 4
    assert r.steps[0].checkpoint == "step R1 of the model solution" and r.steps[2].checkpoint == "step R3 of the model solution"


def test_a_different_valid_method_is_not_marked_wrong():
    r = question(Q1, Q1_IV).grade(ACCEPT[9][2])                       # double difference
    statuses = {s.name: s.status for s in r.steps}
    assert r.verdict == "correct"
    assert statuses["R1"] == "match" and statuses["R5"] == "match"   # R5 is the model's R3
    assert statuses["R4"] == "none"


def test_a_step_with_the_right_shape_but_wrong_tuples_is_close_with_an_example():
    r = question(Q1, Q1_IV).grade(
        "R1 := π Dname, Cno σ Dname = 'Computer Science' COURSE\nR2 := π Sid, Dname, Cno ENROLL\n"
        "R3 := R2 ÷ R1\nAnswer := π Sid, Sname, GPA (R3 ⋈ STUDENT)")
    first = r.steps[0]
    assert first.status == "close" and first.checkpoint == "step R1 of the model solution"
    assert first.case["expected"]["rows"] != first.case["student"]["rows"]
    assert r.steps[1].status == "match"


def test_renamed_attributes_still_match():
    r = question(Q1, Q1_IV).grade(
        "R1 := ρ CE(D, C) π Dname, Cno σ Dname = 'Civil Engineering' COURSE\nπ Sid, Sname, GPA STUDENT")
    assert r.verdict == "wrong_in_general"          # the final answer is wrong …
    assert r.steps[0].status == "match" and r.steps[0].renamed   # … but R1 is the model's R1


def test_staff_can_choose_the_checkpoints():
    q = PreparedQuestion(Q1, Q1_IV, checkpoints=[Checkpoint("R3", "students who took every CE course")])
    r = q.grade(Q1_IV)
    assert [s.checkpoint for s in r.steps if s.status == "match"] == ["students who took every CE course"]


def test_suite_round_trips_through_json():
    q = question(Q1, Q1_II)
    again = PreparedQuestion(Q1, Q1_II, suite_json=q.suite.to_json())
    assert len(again.suite.databases) == len(q.suite.databases)
    assert again.grade(Q1_II.replace("MIN", "MAX")).verdict == "wrong_in_general"


def test_default_checkpoint_labels_never_reveal_the_model_answer():
    r = question(Q1, Q1_IV).grade(Q1_IV.replace("Civil Engineering", "Computer Science"))
    for step in r.steps:
        assert "Civil Engineering" not in (step.checkpoint or "")
