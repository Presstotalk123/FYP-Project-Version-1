"""The RA evaluator reproduces the worked examples of the course slides.

Each test uses the data and the expected result printed on a slide of CZ2007/SC2207
Topic 5 (lectures 1–3) — the course's own definition of the semantics.
"""
import pytest

from app.core.ra import Database, RAError, evaluate, parse


def run(db, text):
    r = evaluate(parse(text), db)
    return r.columns, sorted(r.rows, key=lambda row: [str(v) for v in row])


GRADES = Database.from_dict({"Grades": (["Name", "Course", "Grade"], [
    ("Alice", "DB", "A"), ("Alice", "DM", "C"), ("Bob", "DB", "B"),
    ("Bob", "AI", "B"), ("Cathy", "CG", "A"), ("David", "NN", "C")])})

GRADES_SCHOOLS = Database.from_dict({
    "Grades": (["Name", "Course", "Grade"], [
        ("Alice", "DB", "A"), ("Alice", "DM", "C"), ("Bob", "DB", "B"),
        ("Bob", "NN", "B"), ("Cathy", "SP", "B"), ("Cathy", "NN", "A")]),
    "CrsSch": (["Course", "School"], [
        ("DB", "SCSE"), ("DM", "SCSE"), ("AI", "SCSE"), ("NN", "EEE"), ("SP", "EEE")])})

QUIZZES = Database.from_dict({
    "Quiz1": (["Name", "Score"], [("Alice", 70), ("Bob", 90), ("Cathy", 80), ("David", 100)]),
    "Quiz2": (["Name", "Score"], [("Alice", 80), ("Bob", 90), ("Cathy", 90), ("David", 70)]),
    "Quiz3": (["Name", "Score"], [("Alice", 90), ("Bob", 90), ("Cathy", 80), ("David", 70)])})

STUDENTS = Database.from_dict({"Students": (["ID", "Name", "Age", "School"], [
    (1234, "Alice", 20, "SCSE"), (5678, "Bob", 20, "EEE"), (3742, "Cathy", 22, "SCSE"), (9413, "David", 21, "CEE")])})

DONATIONS = Database.from_dict({
    "Students": (["Name", "School"], [("Alice", "SCSE"), ("Bob", "EEE"), ("Cathy", "CEE"), ("David", "SCSE")]),
    "Donations": (["Name", "Amount"], [("Cathy", 100), ("David", 200), ("Eddie", 300), ("Fred", 400)])})

VOLUNTEERS = Database.from_dict({
    "Students": (["Name", "Age"], [("Alice", 20), ("Bob", 21), ("Cathy", 22), ("David", 21)]),
    "Volunteer": (["Name", "Age"], [("Cathy", 22), ("David", 21), ("Eddie", 43), ("Fred", 35)])})


# ── lecture 1: σ Π ∪ ∩ − ⋈ ×  ────────────────────────────────────────────────
def test_selection_with_and_or():                                        # L1 slides 8–10
    assert run(STUDENTS, "σ School = 'SCSE' AND Age < 21 Students")[1] == [(1234, "Alice", 20, "SCSE")]
    assert len(run(STUDENTS, "σ School = 'SCSE' OR Age < 21 Students")[1]) == 3


def test_projection_and_combining_operators():                           # L1 slides 11–12
    assert run(STUDENTS, "Π ID, Name (σ School = ‘SCSE’ Students)") == (
        ["ID", "Name"], [(1234, "Alice"), (3742, "Cathy")])


def test_selection_after_projection_is_an_error():                       # L1 slide 13
    with pytest.raises(RAError) as e:
        run(STUDENTS, "σ School = 'SCSE' (Π ID, Name Students)")
    assert e.value.code == "RA003" and "select before you project" in e.value.hint


def test_set_operations_remove_duplicates():                             # L1 slides 14, 18, 20–21
    assert len(run(VOLUNTEERS, "Students ∪ Volunteer")[1]) == 6
    assert run(VOLUNTEERS, "Students ∩ Volunteer")[1] == [("Cathy", 22), ("David", 21)]
    assert run(VOLUNTEERS, "Students - Volunteer")[1] == [("Alice", 20), ("Bob", 21)]
    assert run(VOLUNTEERS, "Volunteer - Students")[1] == [("Eddie", 43), ("Fred", 35)]


def test_union_needs_the_same_attributes():                              # L1 slide 17
    db = Database.from_dict({"Students": (["Name", "Age"], [("Alice", 20)]),
                             "Volunteer": (["Name"], [("Cathy",)])})
    with pytest.raises(RAError) as e:
        run(db, "Students ∪ Volunteer")
    assert e.value.code == "RA005"
    assert run(db, "(Π Name Students) ∪ Volunteer")[1] == [("Alice",), ("Cathy",)]


def test_projection_keeps_duplicates():                                  # L1 slide 27
    names = [r[0] for r in run(GRADES, "Π Name Grades")[1]]
    assert names.count("Bob") == 2 and names.count("Alice") == 2


def test_never_taken_dm():                                               # L1 slides 25–27
    assert [r[0] for r in run(GRADES, "(Π Name Grades) - (Π Name σ Course = 'DM' Grades)")[1]] == \
        ["Bob", "Cathy", "David"]
    # the "wrong" attempt on slide 25 keeps Alice
    assert "Alice" in [r[0] for r in run(GRADES, "σ Course ≠ 'DM' Grades")[1]]


def test_db_and_dm_but_not_ai_or_cg():                                   # L1 slide 24
    q = ("((Π Name σ Course = 'DB' Grades) ∩ (Π Name σ Course = 'DM' Grades)) - "
         "((Π Name σ Course = 'AI' Grades) ∪ (Π Name σ Course = 'CG' Grades))")
    assert run(GRADES, q)[1] == [("Alice",)]


def test_natural_join_keeps_common_attribute_once():                     # L1 slides 29–30
    assert run(DONATIONS, "Students ⋈ Donations") == (
        ["Name", "School", "Amount"], [("Cathy", "CEE", 100), ("David", "SCSE", 200)])
    assert run(DONATIONS, "(σ School = 'SCSE' Students) ⋈ Donations")[1] == [("David", "SCSE", 200)]


def test_schools_exercises():                                            # L1 slides 31, 33
    assert run(GRADES_SCHOOLS, "Π Name ( Grades ⋈ (σ School = 'SCSE' CrsSch) ) - "
                               "Π Name ( Grades ⋈ (σ School = 'EEE' CrsSch) )")[1] == [("Alice",)]
    assert run(GRADES_SCHOOLS, "Π Name Grades - (Π Name (Grades ⋈ (σ School <> 'EEE' CrsSch)))")[1] == \
        [("Cathy",)]


def test_theta_join_keeps_both_attributes():                             # L1 slide 35
    cols, rows = run(QUIZZES, "Quiz1 ⋈ Quiz1.Name = Quiz2.Name AND Quiz1.Score < Quiz2.Score Quiz2")
    assert cols == ["Quiz1.Name", "Quiz1.Score", "Quiz2.Name", "Quiz2.Score"]
    assert rows == [("Alice", 70, "Alice", 80), ("Cathy", 80, "Cathy", 90)]


def test_cartesian_product():                                            # L1 slide 36
    db = Database.from_dict({"Students": (["Name", "Age"], [("Alice", 19), ("Bob", 22)]),
                             "Courses": (["ID", "Title"], [("C1", "DB"), ("C2", "Algo")])})
    assert len(run(db, "Students × Courses")[1]) == 4


# ── lecture 2: := ρ δ extended Π γ ──────────────────────────────────────────
def test_assignment_and_rename():                                        # L2 slides 5, 7, 8
    prog = """R1 := σ Name='Cathy' Quiz1
R2 := ρ R2(Name1, Score1, Name2, Score2) (Quiz1 ⋈ Quiz1.Score > R1.Score R1)
R3 := Π Name1, Score1 R2"""
    assert run(QUIZZES, prog) == (["Name1", "Score1"], [("Bob", 90), ("David", 100)])


def test_highest_score_without_aggregation():                            # L2 slide 9
    prog = """R1 := Quiz1
R2 := Quiz1 ⋈ Quiz1.Name <> R1.Name AND Quiz1.Score < R1.Score R1
R3 := Π Quiz1.Name R2
R4 := Π Name Quiz1 - R3"""
    assert run(QUIZZES, prog)[1] == [("David",)]


def test_scores_keep_increasing():                                       # L2 slide 10
    q = ("(Quiz1 ⋈ Quiz1.Name = Quiz2.Name AND Quiz1.Score < Quiz2.Score Quiz2) "
         "⋈ Quiz2.Name = Quiz3.Name AND Quiz2.Score < Quiz3.Score Quiz3")
    assert [r[0] for r in run(QUIZZES, q)[1]] == ["Alice"]


def test_duplicate_elimination():                                        # L2 slide 11
    db = Database.from_dict({"Purchase": (["Name", "Product", "Date"], [
        ("Alice", "iPhone", "2017.01.01"), ("Bob", "Xbox", "2017.01.01"),
        ("Cathy", "iPhone", "2017.01.01"), ("David", "Xbox", "2017.02.17")])})
    r1 = run(db, "Π Product (σ Date='2017.01.01' Purchase)")[1]
    assert len(r1) == 3
    assert run(db, "R1 := Π Product (σ Date='2017.01.01' Purchase)\nR2 := δ(R1)")[1] == [("Xbox",), ("iPhone",)]


def test_extended_projection():                                          # L2 slides 12–13
    db = Database.from_dict({"Scores": (["Name", "Quiz1", "Quiz2"], [
        ("Alice", 70, 90), ("Bob", 90, 80), ("Cathy", 80, 100), ("David", 100, 90)])})
    assert run(db, "Π Name, Quiz1 + Quiz2 → Total Scores")[1] == [
        ("Alice", 160), ("Bob", 170), ("Cathy", 180), ("David", 190)]
    assert run(db, "Π Name, (Quiz1 + Quiz2)/2 → Average Scores") == (
        ["Name", "Average"], [("Alice", 80.0), ("Bob", 85.0), ("Cathy", 90.0), ("David", 95.0)])


def test_grouping_and_aggregation():                                     # L2 slides 14–21
    db = Database.from_dict({"Quiz1": (["Name", "School", "Score"], [
        ("Alice", "SCSE", 90), ("Bob", "EEE", 80), ("Cathy", "EEE", 100), ("David", "SCSE", 90)])})
    assert run(db, "γ MAX(Score) → MaxScore Quiz1")[1] == [(100,)]
    assert run(db, "γ MIN(Score) → MinScore Quiz1")[1] == [(80,)]
    assert run(db, "γ AVG(Score) → AvgScore Quiz1")[1] == [(90.0,)]
    assert run(db, "γ SUM(Score) → SumScore Quiz1")[1] == [(360,)]
    assert run(db, "γ COUNT(Name) → NumStu Quiz1")[1] == [(4,)]
    gpa = Database.from_dict({"Quiz1": (["Name", "School", "GPA"], [
        ("Alice", "SCSE", 4), ("Bob", "EEE", 3), ("Cathy", "EEE", 3.4), ("David", "SCSE", 3.6)])})
    cols, rows = run(gpa, "γ School, AVG(GPA) → AvgGPA, MAX(GPA) → MaxGPA Quiz1")
    assert cols == ["School", "AvgGPA", "MaxGPA"]
    assert [(s, round(a, 2), m) for s, a, m in rows] == [("EEE", 3.2, 3.4), ("SCSE", 3.8, 4)]


def test_aggregate_in_selection_is_an_error():                           # L2 slide 23
    with pytest.raises(RAError) as e:
        parse("σ Score = MAX(Score) Quiz1")
    assert e.value.code == "RA013"


def test_highest_score_with_aggregation():                               # L2 slide 23
    prog = "R1 := γ MAX(Score)→MaxScore(Quiz1)\nR2 := Quiz1 ⋈ Score = MaxScore R1\nR3 := Π Name(R2)"
    assert run(QUIZZES, prog)[1] == [("David",)]


# ── lecture 3: ÷ and outer joins ─────────────────────────────────────────────
OWNS = Database.from_dict({
    "Owns": (["Name", "Product"], [("Alice", "iPad"), ("Alice", "iPhone"), ("Bob", "iPhone"), ("Cathy", "iPad")]),
    "AppleP": (["Product", "Price"], [("iPhone", 999), ("iPad", 699)])})


def test_division():                                                     # L3 slides 5, 8
    assert run(OWNS, "Owns ÷ (Π Product AppleP)") == (["Name"], [("Alice",)])
    with pytest.raises(RAError) as e:
        run(OWNS, "Owns ÷ AppleP")
    assert e.value.code == "RA006" and "Price" in e.value.hint


def test_division_keeps_every_other_attribute():                         # L3 slide 9
    db = Database.from_dict({
        "Owns": (["Name", "Since", "Product"], [("Alice", 2013, "iPhone"), ("Alice", 2013, "iPad"),
                                                ("Bob", 2013, "iPhone"), ("Bob", 2010, "iPad")]),
        "AppleP": (["Product"], [("iPhone",), ("iPad",)])})
    assert run(db, "Owns ÷ AppleP") == (["Name", "Since"], [("Alice", 2013)])


def test_joins_divided_by_clubs():                                       # L3 slides 6–7
    db = Database.from_dict({
        "Joins": (["Name", "Club"], [("Alice", "ABC"), ("Bob", "DEF"), ("Bob", "ABC"), ("Cathy", "DEF")]),
        "Clubs": (["Club"], [("ABC",), ("DEF",)])})
    assert run(db, "Joins ÷ Clubs")[1] == [("Bob",)]


def test_outer_joins():                                                  # L3 slides 12–16
    assert run(DONATIONS, "Students ⟕ Donations")[1] == [
        ("Alice", "SCSE", None), ("Bob", "EEE", None), ("Cathy", "CEE", 100), ("David", "SCSE", 200)]
    assert run(DONATIONS, "Students ⟖ Donations")[1] == [
        ("Cathy", "CEE", 100), ("David", "SCSE", 200), ("Eddie", None, 300), ("Fred", None, 400)]
    assert len(run(DONATIONS, "Students ⟗ Donations")[1]) == 6


def test_outer_join_with_condition_keeps_all_attributes():               # L3 slide 13
    db = Database.from_dict({
        "Students": (["SName", "School"], [("Alice", "SCSE"), ("Cathy", "CEE")]),
        "Donations": (["Name", "Amount"], [("Cathy", 100), ("Eddie", 300)])})
    assert run(db, "Students ⟕ SName = Name Donations") == (
        ["SName", "School", "Name", "Amount"], [("Alice", "SCSE", None, None), ("Cathy", "CEE", "Cathy", 100)])


def test_count_male_stars_needs_outer_join():                            # L3 slides 18–21
    db = Database.from_dict({
        "CastIn": (["Name", "Movie", "Year"], [("John", "Batman", 2012), ("Steve", "Batman", 2012),
                                              ("Meg", "The Women", 2008)]),
        "Stars": (["Name", "Gender", "Birth"], [("John", "Male", 1980), ("Meg", "Female", 1981),
                                               ("Steve", "Male", 1990)])})
    inner = "R1 := σ Gender = 'Male' Stars\nR2 := CastIn ⋈ R1\nγ Movie, COUNT(Gender) → MaleStars (R2)"
    assert run(db, inner)[1] == [("Batman", 2)]                       # "Incomplete!"
    outer = "R1 := σ Gender = 'Male' Stars\nR2 := CastIn ⟕ R1\nγ Movie, COUNT(Gender) → MaleStars (R2)"
    assert run(db, outer)[1] == [("Batman", 2), ("The Women", 0)]


# ── notation and evaluation details ──────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "Π ID, Name (σ School = 'SCSE' Students)",
    "Π_{ID, Name}(σ_{School = 'SCSE'}(Students))",
    "π[ID, Name](σ[School = 'SCSE'](Students))",
    "\\project_{ID, Name} \\select_{School = \"SCSE\"} Students",
    "R1 := σ School = “SCSE” Students; Π ID, Name R1",
])
def test_notations_agree(text):
    assert run(STUDENTS, text)[1] == [(1234, "Alice"), (3742, "Cathy")]


def test_trace_records_every_step():
    r = evaluate(parse("R1 := σ School = 'SCSE' Students\nΠ Name R1"), STUDENTS)
    assert [s["name"] for s in r.statements] == ["R1", None]
    first = r.statements[0]["tree"]
    assert first["label"] == "σ School = 'SCSE'" and first["row_count"] == 2
    assert first["children"][0]["label"] == "Students"
    assert r.statements[1]["tree"]["columns"] == ["Name"]


def test_huge_products_are_stopped():
    db = Database.from_dict({"R": (["a"], [(i,) for i in range(600)])})
    with pytest.raises(RAError) as e:
        evaluate(parse("ρ S(b) R × ρ T(c) R"), db, max_rows=100_000)
    assert e.value.code == "RA100" and "⋈" in e.value.hint
