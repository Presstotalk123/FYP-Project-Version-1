"""Example data for questions without data (core/ra/example_data.py)."""
from app.core.ra import Database, evaluate, parse
from app.core.ra.example_data import build_example, to_insert_sql
from app.core.ra.example_values import realistic_values, words

SCHEMA = """CREATE TABLE DEPT (Dname TEXT PRIMARY KEY, Numphds INTEGER);
CREATE TABLE PROF (Pname TEXT PRIMARY KEY, Dname TEXT REFERENCES DEPT(Dname));
CREATE TABLE STUDENT (Sid INTEGER PRIMARY KEY, Sname TEXT, Age INTEGER, Year INTEGER, GPA REAL);
CREATE TABLE MAJOR (Dname TEXT REFERENCES DEPT(Dname), Sid INTEGER REFERENCES STUDENT(Sid), PRIMARY KEY (Dname, Sid));"""
ANSWERS = ["R1 := σ Numphds < 50 (DEPT)\nπ Pname (PROF ⋈ R1)", "π Sid STUDENT − π Sid MAJOR"]


def test_same_question_same_data_and_variants_differ():
    first = to_insert_sql(build_example(SCHEMA, ANSWERS))
    assert first == to_insert_sql(build_example(SCHEMA, ANSWERS))
    assert first != to_insert_sql(build_example(SCHEMA, ANSWERS, variant=1))


def test_it_fits_the_schema_and_has_three_to_five_tuples():
    db = build_example(SCHEMA, ANSWERS)
    assert all(3 <= len(t.rows) <= 5 for t in db.tables)
    again = Database.from_sql(SCHEMA, to_insert_sql(db))           # keys and foreign keys hold
    assert [t.rows for t in again.tables] == [t.rows for t in db.tables]


def test_it_shows_what_the_model_answers_do():
    db = build_example(SCHEMA, ANSWERS)
    for answer in ANSWERS:
        assert evaluate(parse(answer, db.names()), db).rows               # no empty answer
    numphds = [row[1] for row in db.lookup("DEPT").rows]
    assert any(n < 50 for n in numphds) and any(n >= 50 for n in numphds)   # σ keeps some, not all


def test_values_look_real():
    assert "Alice" in realistic_values("Sname", "STUDENT", "TEXT")
    assert "Computer Science" in realistic_values("Dname", "PROF", "TEXT")
    assert realistic_values("Year", "STUDENT", "INTEGER") == [1, 2, 3, 4]
    assert all(isinstance(v, float) and 2 <= v <= 5 for v in realistic_values("GPA", "STUDENT", "REAL"))
    assert realistic_values("Cno", "COURSE", "TEXT")[0] == "C101"
    assert realistic_values("Sid", "STUDENT", "INTEGER") == list(range(1, 9))
    assert words("teamid-one") == ["teamid", "one"] and words("firstName") == ["first", "name"]


def test_unreadable_model_answers_are_skipped():
    db = build_example(SCHEMA, ["σ (", *ANSWERS])
    assert all(t.rows for t in db.tables)


def test_quotes_survive_the_insert_statements():
    db = Database.from_sql(SCHEMA).with_rows({"DEPT": [("O'Brien Hall", 3)]})
    assert Database.from_sql(SCHEMA, to_insert_sql(db)).lookup("DEPT").rows == [("O'Brien Hall", 3)]


def test_attributes_named_like_a_key_refer_to_it_even_without_references():
    """Tutorial 5.5 declares no REFERENCES; the example data is still consistent."""
    from app.services.ra.examples import TUTORIAL_Q1
    db = build_example(TUTORIAL_Q1["schema_sql"], ["π Sname (STUDENT ⋈ ENROLL)"])
    rows = lambda name, *cols: {tuple(r[db.lookup(name).column_names.index(c)] for c in cols)  # noqa: E731
                                for r in db.lookup(name).rows}
    assert rows("ENROLL", "Sid") <= rows("STUDENT", "Sid")
    assert rows("ENROLL", "Dname", "Cno", "Sectno") <= rows("SECTION", "Dname", "Cno", "Sectno")
    assert rows("SECTION", "Cno", "Dname") <= rows("COURSE", "Cno", "Dname")
    assert rows("PROF", "Dname") <= rows("DEPT", "Dname") and rows("MAJOR", "Sid") <= rows("STUDENT", "Sid")
