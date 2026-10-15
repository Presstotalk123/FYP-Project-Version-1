"""Tests for the relational-algebra parser and translator (app/core/ra).

The central check is *equivalence*: the translated RA and a hand-written SQL query must
produce the same grading hash (core/answer_validator.generate_hash) when run through
the platform's read-only executor (core/query_executor.execute_student_query) — the
exact path an RA question will take in execute.py.
"""
import sqlite3

import pytest
from hypothesis import given, settings, strategies as st

from app.core.answer_validator import generate_hash
from app.core.query_executor import execute_student_query
from app.core.ra import RAError, Schema, parse, translate
from tests.fyp.ra_fixtures import build_university_db


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    return build_university_db(str(tmp_path_factory.mktemp("ra") / "university.db"))


@pytest.fixture(scope="module")
def schema(db):
    return Schema.from_sqlite(db)


def run(db, sql):
    result = execute_student_query(db, sql)
    assert result["success"], f"{result['error_message']}\n{sql}"
    return result


def ra_hash(db, schema, expr):
    tr = translate(expr, schema)
    r = run(db, tr.sql)
    return generate_hash(r["raw_results"], r["columns"]), r


def sql_hash(db, sql):
    r = run(db, sql)
    return generate_hash(r["raw_results"], r["columns"]), r


# ── equivalence with hand-written SQL ─────────────────────────────────────────
EQUIVALENT = [
    pytest.param(
        "π[name](σ[major = 'CS'](Student))",
        "SELECT DISTINCT name FROM Student WHERE major = 'CS'",
        id="select-project"),
    pytest.param(
        "π[title](σ[credits > 3](Course))",
        "SELECT DISTINCT title FROM Course WHERE credits > 3",
        id="numeric-condition"),
    pytest.param(
        "π[name](σ[title = 'Databases'](Student ⋈ Enrolled ⋈ Course))",
        "SELECT DISTINCT s.name FROM Student s JOIN Enrolled e ON s.sid = e.sid "
        "JOIN Course c ON c.cid = e.cid WHERE c.title = 'Databases'",
        id="three-way-natural-join"),
    pytest.param(
        "π[sid](Student) − π[sid](Enrolled)",
        "SELECT sid FROM Student EXCEPT SELECT sid FROM Enrolled",
        id="difference"),
    pytest.param(
        "π[cid](σ[name = 'Alice'](Student) ⋈ Enrolled) ∩ π[cid](σ[name = 'Chen Wei'](Student) ⋈ Enrolled)",
        "SELECT e.cid FROM Student s JOIN Enrolled e ON s.sid = e.sid WHERE s.name = 'Alice' "
        "INTERSECT SELECT e.cid FROM Student s JOIN Enrolled e ON s.sid = e.sid WHERE s.name = 'Chen Wei'",
        id="intersection"),
    pytest.param(
        "π[sid, cid](Enrolled) ÷ π[cid](σ[dept = 'CS'](Course))",
        "SELECT DISTINCT e.sid FROM Enrolled e WHERE NOT EXISTS (SELECT 1 FROM Course c "
        "WHERE c.dept = 'CS' AND NOT EXISTS (SELECT 1 FROM Enrolled e2 "
        "WHERE e2.sid = e.sid AND e2.cid = c.cid))",
        id="division"),
    pytest.param(
        "π[S1.name, S2.name](ρ[S1](Student) ⋈[S1.major = S2.major ∧ S1.sid < S2.sid] ρ[S2](Student))",
        'SELECT DISTINCT a.name AS "S1.name", b.name AS "S2.name" FROM Student a JOIN Student b '
        "ON a.major = b.major AND a.sid < b.sid",
        id="theta-join-self-pairs"),
    pytest.param(
        "CS ← σ[major = 'CS'](Student); M ← σ[major = 'Math'](Student); π[name](CS) ∪ π[name](M)",
        "SELECT name FROM Student WHERE major = 'CS' UNION SELECT name FROM Student WHERE major = 'Math'",
        id="assignment-union"),
    pytest.param(
        "π[name](Student) − π[S1.name](ρ[S1](Student) ⋈[S1.age < S2.age] ρ[S2](Student))",
        "SELECT name FROM Student WHERE age = (SELECT MAX(age) FROM Student)",
        id="oldest-without-aggregation"),
    pytest.param(
        "π[Student.name, Lecturer.name](σ[Student.major = Lecturer.dept](Student × Lecturer))",
        'SELECT DISTINCT s.name AS "Student.name", l.name AS "Lecturer.name" '
        "FROM Student s, Lecturer l WHERE s.major = l.dept",
        id="product-with-clashing-names"),
    pytest.param(
        "π[n](ρ[X(i, n, a, m)](Student))",
        "SELECT DISTINCT name AS n FROM Student",
        id="rename-attributes"),
    pytest.param(
        "π[name, age](σ[not (age < 21) or major = 'Math'](Student))",
        "SELECT DISTINCT name, age FROM Student WHERE NOT (age < 21) OR major = 'Math'",
        id="not-or"),
    pytest.param(
        "π[name](σ[dept <> cdept](Lecturer ⋈ Teaches ⋈ ρ[C(cid, title, cdept, credits)](Course)))",
        "SELECT DISTINCT l.name FROM Lecturer l JOIN Teaches t ON l.lid = t.lid "
        "JOIN Course c ON c.cid = t.cid WHERE l.dept <> c.dept",
        id="lecturer-outside-department"),
    pytest.param(
        "π[major](Student)",
        "SELECT DISTINCT major FROM Student",
        id="projection-removes-duplicates"),
]


@pytest.mark.parametrize("ra, sql", EQUIVALENT)
def test_equivalent_to_handwritten_sql(db, schema, ra, sql):
    ra_h, ra_r = ra_hash(db, schema, ra)
    sql_h, sql_r = sql_hash(db, sql)
    assert ra_r["row_count"] > 0 or sql_r["row_count"] == 0
    assert ra_h == sql_h, (ra_r["results"], sql_r["results"])


def test_ascii_and_unicode_forms_are_equivalent(db, schema):
    unicode = "π[name](σ[age > 20 ∧ major = 'CS'](Student ⋈ Enrolled))"
    ascii_ = "\\project_{name} \\select_{age > 20 and major = 'CS'} (Student \\join Enrolled)"
    assert ra_hash(db, schema, unicode)[0] == ra_hash(db, schema, ascii_)[0]


def test_known_answers(db, schema):
    _, r = ra_hash(db, schema, "π[sid, cid](Enrolled) ÷ π[cid](σ[dept = 'CS'](Course))")
    assert sorted(row["sid"] for row in r["results"]) == [1, 3]
    _, r = ra_hash(db, schema, "π[name](Student) − π[name](Student ⋈ Enrolled)")
    assert [row["name"] for row in r["results"]] == ["Zoe"]


# ── output naming (the grader hashes column names) ─────────────────────────────
def test_output_attribute_names(schema):
    assert translate("π[name](Student)", schema).output_attributes == ["name"]
    tr = translate("Student × Lecturer", schema)
    assert "Student.name" in tr.output_attributes and "Lecturer.name" in tr.output_attributes
    assert "sid" in tr.output_attributes            # unique names stay bare
    tr = translate("Student ⋈ Enrolled", schema)
    assert tr.output_attributes.count("sid") == 1   # natural join keeps common attrs once


def test_merged_join_attribute_can_be_qualified_by_either_input(db, schema):
    a = ra_hash(db, schema, "π[Student.sid](Student ⋈ Enrolled)")[0]
    b = ra_hash(db, schema, "π[Enrolled.sid](Student ⋈ Enrolled)")[0]
    assert a == b


def test_case_insensitive_names(db, schema):
    assert ra_hash(db, schema, "π[NAME](student)")[0] == ra_hash(db, schema, "π[name](Student)")[0]


# ── tree and metadata for the UI / analytics ──────────────────────────────────
def test_tree_and_operators(schema):
    tr = translate("π[name](σ[age > 20](Student ⋈ Enrolled))", schema)
    assert tr.tree["op"] == "project" and tr.tree["label"] == "π[name]"
    select = tr.tree["children"][0]
    assert select["label"] == "σ[age > 20]"
    join = select["children"][0]
    assert join["op"] == "natural_join"
    assert [c["label"] for c in join["children"]] == ["Student", "Enrolled"]
    assert tr.tree["line"] == 1 and tr.tree["col"] == 1
    assert tr.operators_used == ["project", "select", "natural_join"]


def test_assignments_appear_in_tree(schema):
    tr = translate("A ← σ[age > 20](Student); π[name](A)", schema)
    assert tr.tree["assignments"][0]["name"] == "A"
    assert tr.sql.startswith('WITH "A" AS (')


# ── errors (FYP Design Document 02, §5.5) ─────────────────────────────────────
ERRORS = [
    ("π[name](Student ⋈ )", "RA001"),
    ("σ[age >](Student)", "RA001"),
    ("π[name] Student @", "RA001"),
    ("π[name](Students)", "RA002"),
    ("σ[Students.age > 1](Student)", "RA002"),
    ("π[nme](Student)", "RA003"),
    ("π[sid](Student × Enrolled)", "RA004"),
    ("π[sid](Student) ∪ π[sid, name](Student)", "RA005"),
    ("π[sid](Student) ÷ π[cid](Course)", "RA006"),
    ("π[cid](Enrolled) ÷ π[cid](Course)", "RA006"),
    ("ρ[S(a, b)](Student)", "RA007"),
    ("π[name, name](Student)", "RA010"),
    ("Student × Student", "RA011"),
    ("Student ← π[sid](Student); Student", "RA012"),
    ("x" * 6000, "RA009"),
]


@pytest.mark.parametrize("expr, code", ERRORS)
def test_error_codes(schema, expr, code):
    with pytest.raises(RAError) as exc:
        translate(expr, schema)
    assert exc.value.code == code, str(exc.value)


def test_error_messages_help_the_student(schema):
    with pytest.raises(RAError) as exc:
        translate("π[nme](Student)", schema)
    err = exc.value
    assert "nme" in err.message and "Did you mean “name”?" == err.hint
    assert (err.line, err.col) == (1, 3)

    with pytest.raises(RAError) as exc:
        translate("π[name](Studnet)", schema)
    assert exc.value.hint == "Did you mean “Student”?"

    with pytest.raises(RAError) as exc:
        translate("π[sid](Student × Enrolled)", schema)
    assert "Student.sid or Enrolled.sid" in exc.value.message


def test_type_mismatch_is_a_warning_not_an_error(db, schema):
    tr = translate("σ[name = 20](Student)", schema)
    assert [w.code for w in tr.warnings] == ["RA008"]
    run(db, tr.sql)


def test_deep_nesting_rejected(schema):
    expr = "σ[age > 1](" * 70 + "Student" + ")" * 70
    with pytest.raises(RAError) as exc:
        parse(expr)
    assert exc.value.code == "RA009"


# ── security (FYP Design Document 02, §8) ─────────────────────────────────────
def test_generated_sql_is_read_only(schema):
    for param in EQUIVALENT:
        sql = translate(param.values[0], schema).sql
        assert sql.split()[0] in ("SELECT", "WITH")


def test_string_literals_cannot_inject_sql(db, schema):
    evil = "σ[name = 'x''; DROP TABLE Student; --'](Student)"
    tr = translate(evil, schema)

    # Layer 1 — the translator: the attack stays one escaped string literal, so the
    # generated SQL is a single harmless SELECT that simply matches no student.
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    assert conn.execute(tr.sql).fetchall() == []
    conn.close()

    # Layer 2 — the inherited read-only executor rejects any query mentioning DROP,
    # even inside a string, so it never runs at all.
    assert execute_student_query(db, tr.sql)["success"] is False

    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM Student").fetchone()[0] == 7
    conn.close()


def test_identifiers_must_exist_in_schema(schema):
    with pytest.raises(RAError):
        translate("π[name](sqlite_master)", schema)


# ── algebraic laws hold on random inputs (property-based) ─────────────────────
STUDENT_ATTRS = ["sid", "name", "age", "major"]
attr_subsets = st.lists(st.sampled_from(STUDENT_ATTRS), min_size=1, max_size=4, unique=True)
ages = st.integers(min_value=15, max_value=26)
ops = st.sampled_from(["<", "<=", ">", ">=", "=", "<>"])


@settings(max_examples=40, deadline=None)
@given(attrs=attr_subsets, op=ops, k=ages)
def test_property_select_project_matches_sql(db, schema, attrs, op, k):
    ra = f"π[{', '.join(attrs)}](σ[age {op} {k}](Student))"
    sql = f"SELECT DISTINCT {', '.join(attrs)} FROM Student WHERE age {op} {k}"
    assert ra_hash(db, schema, ra)[0] == sql_hash(db, sql)[0]


@settings(max_examples=25, deadline=None)
@given(op=ops, k=ages, j=ages)
def test_property_selection_distributes_over_union(db, schema, op, k, j):
    lhs = f"σ[age {op} {k}](σ[age < {j}](Student) ∪ σ[major = 'CS'](Student))"
    rhs = f"σ[age {op} {k}](σ[age < {j}](Student)) ∪ σ[age {op} {k}](σ[major = 'CS'](Student))"
    assert ra_hash(db, schema, lhs)[0] == ra_hash(db, schema, rhs)[0]


@settings(max_examples=15, deadline=None)
@given(k=ages)
def test_property_natural_join_commutes(db, schema, k):
    a = f"σ[age > {k}](Student) ⋈ Enrolled"
    b = f"Enrolled ⋈ σ[age > {k}](Student)"
    assert ra_hash(db, schema, a)[0] == ra_hash(db, schema, b)[0]
