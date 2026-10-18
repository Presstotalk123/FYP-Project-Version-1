"""Behaviour added or fixed when the prototype engine moved into app/core/ra.

Each test names the problem it pins down, so a regression points straight at it.
"""
import pytest

from app.core.ra import Database, EvalOptions, RAError, evaluate, parse
from app.core.ra.normalize import normalize


def run(db, text, **kw):
    r = evaluate(parse(text, db.names()), db, **kw)
    return r.columns, sorted(r.rows, key=lambda row: [str(v) for v in row])


QUIZ = Database.from_dict({
    "Quiz1": (["Name", "Score"], [("Alice", 70), ("Bob", 50), ("Cara", None)]),
    "Quiz2": (["Name", "Score"], [("Alice", 90), ("Dan", 60)])})


# ── NULLs: three-valued logic ─────────────────────────────────────────────────
@pytest.mark.parametrize("cond, names", [
    ("Score > 60", ["Alice"]),
    ("NOT (Score > 60)", ["Bob"]),                         # Cara's NULL is unknown, not false
    ("Score > 60 OR NOT (Score > 60)", ["Alice", "Bob"]),  # unknown OR unknown is unknown
    ("NOT (Score > 60 AND Name = 'Cara')", ["Alice", "Bob"]),
    ("Score > 60 OR Name = 'Cara'", ["Alice", "Cara"]),    # unknown OR true is true
])
def test_conditions_on_null_are_unknown(cond, names):
    assert [r[0] for r in run(QUIZ, f"σ {cond} Quiz1")[1]] == names


def test_theta_join_drops_unknown_matches():
    db = Database.from_dict({"A": (["x"], [(1,), (None,)]), "B": (["y"], [(1,), (None,)])})
    assert run(db, "A ⋈ NOT (x <> y) B")[1] == [(1, 1)]


# ── pasted symbols ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("pasted", [
    "Quiz1 ⨝ Quiz2",              # ⨝ from Word's equation editor
    "∏ Name Quiz1",               # ∏ used for projection
    "Π Name Quiz1",          # non-breaking space
    "(Π Name Quiz1) – (Π Name Quiz2)",   # en dash from Word's auto-correct
    "﻿Π Name Quiz1",         # byte-order mark at the start of a paste
])
def test_pasted_lookalike_symbols_are_accepted(pasted):
    evaluate(parse(pasted), QUIZ)


def test_normalize_keeps_every_column_in_place():
    text = "R1 := ∏ Name Quiz1 ⨝ Quiz2"
    assert len(normalize(text)) == len(text)
    with pytest.raises(RAError) as e:
        parse("∏ Name Quiz1 ⨝ @")
    assert e.value.col == 16


# ── ρ S (R) ───────────────────────────────────────────────────────────────────
def test_rename_with_relation_in_brackets():
    assert run(QUIZ, "ρ S (Quiz1)")[0] == ["Name", "Score"]
    assert run(QUIZ, "Π S.Name (ρ S (Π Name Quiz1 ⋈ Π Name Quiz2))") == (["Name"], [("Alice",)])


def test_rename_with_attribute_list_still_wins():
    assert run(QUIZ, "ρ S(N, Sc) Quiz1")[0] == ["N", "Sc"]
    assert run(QUIZ, "ρ S (N, Sc) Quiz1")[0] == ["N", "Sc"]


def test_rename_in_brackets_then_join():
    cols, _ = run(QUIZ, "ρ Q (Quiz1) ⋈ Q.Name = Quiz2.Name Quiz2")
    assert cols == ["Q.Name", "Q.Score", "Quiz2.Name", "Quiz2.Score"]


# ── hyphenated schema names (Tutorial 5.5 Q3) ────────────────────────────────
SOCCER = Database.from_sql(
    'CREATE TABLE Results ("teamid-one" INT, "teamid-two" INT, scoreone INT, scoretwo INT, '
    'matchdate TEXT, PRIMARY KEY ("teamid-one", "teamid-two", matchdate));',
    "INSERT INTO Results VALUES (1, 2, 1, 1, 'd1'), (1, 2, 0, 0, 'd2'), (1, 3, 2, 2, 'd1'), (1, 3, 0, 1, 'd2');")


def test_hyphenated_attribute_names():
    q = ("R1 := Π teamid-one, teamid-two Results\n"
         "R2 := Π teamid-one, teamid-two σ scoreone <> scoretwo Results\n"
         "R1 − R2")
    assert run(SOCCER, q) == (["teamid-one", "teamid-two"], [(1, 2)])


def test_hyphen_is_still_minus_between_relations():
    assert run(SOCCER, "R1 := Π scoreone Results\nR2 := Π scoretwo Results\nR1-ρ R1(scoreone) R2")[1] == []


def test_hyphen_inside_a_string_is_left_alone():
    assert run(SOCCER, "σ matchdate = 'teamid-one' Results")[1] == []


# ── schema loader ─────────────────────────────────────────────────────────────
def test_schema_keeps_keys_and_foreign_keys():
    db = Database.from_sql("""
        CREATE TABLE DEPT (Dname TEXT PRIMARY KEY, Numphds INT);
        CREATE TABLE PROF (Pname TEXT PRIMARY KEY, Dname TEXT NOT NULL REFERENCES DEPT(Dname));
    """)
    dept, prof = db.lookup("dept"), db.lookup("PROF")
    assert dept.primary_key == ["Dname"] and dept.rows == []
    assert prof.not_null == ["Pname", "Dname"]
    assert [(fk.columns, fk.ref_table, fk.ref_columns) for fk in prof.foreign_keys] == [(["Dname"], "DEPT", ["Dname"])]
    assert [c for c, _ in dept.columns] == ["Dname", "Numphds"] and dept.columns[1][1] == "INTEGER"


def test_schema_tables_keep_the_order_staff_wrote():
    db = Database.from_sql("CREATE TABLE Zed (a INT); CREATE TABLE Alpha (b INT);")
    assert [t.name for t in db.tables] == ["Zed", "Alpha"]


@pytest.mark.parametrize("schema, data", [
    ("CREATE TABLE T (a INT", ""),
    ("CREATE TABLE T (a INT);", "INSERT INTO Missing VALUES (1);"),
    ("ATTACH DATABASE '/tmp/ra_should_not_exist.db' AS other;", ""),
    ("PRAGMA writable_schema = 1; CREATE TABLE T (a INT);", ""),
    ("", ""),
    ("CREATE TABLE T (a INT); WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c) "
     "INSERT INTO T SELECT x FROM c;", ""),
])
def test_bad_or_unsafe_schema_sql_is_rejected(schema, data):
    with pytest.raises(RAError) as e:
        Database.from_sql(schema, data)
    assert e.value.code == "RA020"


# ── aggregates and NULL: SQL rule vs the lecture 3 slides ────────────────────
MOVIES = Database.from_dict({
    "CastIn": (["Name", "Movie", "Year"], [("John", "Batman", 2012), ("Steve", "Batman", 2012),
                                          ("Meg", "The Women", 2008)]),
    "Stars": (["Name", "Gender", "Birth"], [("John", "Male", 1980), ("Meg", "Female", 1981),
                                           ("Steve", "Male", 1990)])})
SLIDE_20 = "R1 := σ Gender = 'Male' Stars\nR2 := CastIn ⟕ R1\nγ Movie, COUNT(Gender) → MaleStars (R2)"
SLIDE_21 = ("R1 := σ Gender = 'Male' Stars\nR2 := γ Name, COUNT(Gender) → Male (R1)\n"
            "R3 := CastIn ⟕ R2\nγ Movie, SUM(Male) → MaleStars (R3)")


def test_slides_rule_reproduces_lecture_3_slides_20_and_21():
    slides = EvalOptions(aggregate_nulls="slides")
    assert run(MOVIES, SLIDE_20, options=slides)[1] == [("Batman", 2), ("The Women", 1)]
    assert run(MOVIES, SLIDE_21, options=slides)[1] == [("Batman", 2), ("The Women", 0)]


def test_sql_rule_is_the_default():
    assert run(MOVIES, SLIDE_20)[1] == [("Batman", 2), ("The Women", 0)]
    assert run(MOVIES, SLIDE_21)[1] == [("Batman", 2), ("The Women", None)]


# ── runaway work is stopped before it starts ─────────────────────────────────
def test_product_is_refused_before_it_is_built():
    db = Database.from_dict({"R": (["a"], [(i,) for i in range(2000)])})
    with pytest.raises(RAError) as e:
        evaluate(parse("ρ S(b) R × ρ T(c) R × ρ U(d) R"), db)
    assert e.value.code == "RA100"


def test_theta_join_work_is_capped():
    db = Database.from_dict({"R": (["a"], [(i,) for i in range(2000)])})
    with pytest.raises(RAError) as e:
        evaluate(parse("ρ S(b) R ⋈ b < c ρ T(c) R"), db)
    assert e.value.code == "RA100" and "pairs" in e.value.message


# ── the semantics the grader depends on ───────────────────────────────────────
def test_count_method_for_all_is_fooled_by_retakes():
    """Lecture 2 slide 28's count method counts a retaken course twice; ÷ does not."""
    db = Database.from_dict({
        "Takes": (["Sid", "Cno", "Sem"], [(1, "C1", 1), (1, "C2", 1), (2, "C1", 1), (2, "C1", 2)]),
        "Course": (["Cno", "Dept"], [("C1", "CE"), ("C2", "CE"), ("C3", "CS")])})
    ce = "R1 := Π Cno σ Dept = 'CE' Course\n"
    division = ce + "(Π Sid, Cno Takes) ÷ R1"
    counting = ce + ("R2 := γ COUNT(Cno) → N R1\nR3 := γ Sid, COUNT(Cno) → M (Takes ⋈ R1)\n"
                     "Π Sid (σ M = N (R3 × R2))")
    assert run(db, division)[1] == [(1,)]
    assert run(db, counting)[1] == [(1,), (2,)]
