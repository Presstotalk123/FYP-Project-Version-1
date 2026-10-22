"""A schema written as plain text becomes CREATE TABLE statements the engine can load."""
import pytest

from app.core.ra import Database, RAError
from app.core.ra.text_schema import sql_from_text

UNIVERSITY = """Consider the university database below (keys are marked with *):

- STUDENT(*Sid, Sname, Sex, Age, Year, GPA)
- DEPT(*Dname, Numphds)
- PROF(*Pname, Dname)
- COURSE(*Cno, Cname, *Dname)
- MAJOR(*Dname, *Sid)
- SECTION(*Dname, *Cno, *Sectno, Pname)
- ENROLL(*Sid, Grade, *Dname, *Cno, *Sectno)

Find the name(s) of student(s) with the lowest GPA.
"""


def tables(sql):
    return {t.name: t for t in Database.from_sql(sql).tables}


def test_the_tutorial_schema_converts_and_loads():
    sql = sql_from_text(UNIVERSITY)
    assert sql.splitlines()[0] == ("CREATE TABLE STUDENT (Sid INTEGER PRIMARY KEY, Sname TEXT, Sex TEXT, "
                                   "Age INTEGER, Year INTEGER, GPA REAL);")
    t = tables(sql)
    assert list(t) == ["STUDENT", "DEPT", "PROF", "COURSE", "MAJOR", "SECTION", "ENROLL"]   # not name(s)
    assert t["COURSE"].primary_key == ["Cno", "Dname"]
    assert dict(t["ENROLL"].columns)["Grade"] == "REAL" and dict(t["DEPT"].columns)["Numphds"] == "INTEGER"
    links = {(tuple(fk.columns), fk.ref_table) for fk in t["ENROLL"].foreign_keys}
    assert links == {(("Sid",), "STUDENT"), (("Dname",), "DEPT"), (("Cno", "Dname"), "COURSE"),
                     (("Dname", "Cno", "Sectno"), "SECTION")}
    assert {fk.ref_table for fk in t["PROF"].foreign_keys} == {"DEPT"}
    assert t["STUDENT"].foreign_keys == []


def test_links_can_be_left_out():
    assert all(not t.foreign_keys for t in tables(sql_from_text(UNIVERSITY, link=False)).values())


def test_same_key_relations_are_not_linked_to_each_other():
    t = tables(sql_from_text("STUDENT(*Sid, Sname)\nGRAD(*Sid, Thesis)\nTA(*Sid, *Cno)"))
    assert t["GRAD"].foreign_keys == [] and t["STUDENT"].foreign_keys == []
    assert {fk.ref_table for fk in t["TA"].foreign_keys} == set()      # Sid could be either's


def test_types_can_be_written_and_names_with_hyphens_are_quoted():
    sql = sql_from_text("`TEAM(*teamid-one, city: TEXT, founded DATE, budget REAL)`, PLAYER(*pid, team)")
    assert sql.splitlines()[0] == ('CREATE TABLE TEAM ("teamid-one" TEXT PRIMARY KEY, city TEXT, founded TEXT, '
                                   'budget REAL);')
    assert list(tables(sql)) == ["TEAM", "PLAYER"]


def test_a_relation_may_span_lines():
    t = tables(sql_from_text("RESERVATIONS(*passenger_ssn, *train_num,\n   *date, seat_number)"))
    assert t["RESERVATIONS"].primary_key == ["passenger_ssn", "train_num", "date"]


@pytest.mark.parametrize("text, message, line", [
    ("R(*A, B)\nR(C)", "written twice", 2),
    ("R(A,, B)", "empty attribute", 1),
    ("R(A, B C D)", "not an attribute name", 1),
    ("R(A, a)", "attribute a twice", 1),
    ("Just some text.", "No relations found", 1),
])
def test_mistakes_point_at_their_line(text, message, line):
    with pytest.raises(RAError) as e:
        sql_from_text(text)
    assert message in e.value.message and e.value.line == line and e.value.code == "RA020"
