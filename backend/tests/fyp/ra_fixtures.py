"""A small university database shared by the RA tests (FYP Design Document 02, §12).

The data is chosen so that common mistakes give visibly different answers, e.g. Zoe is
enrolled in nothing, Alice and Chen Wei both take every CS course, and lecturer Tan
teaches outside their own department.
"""
import sqlite3

UNIVERSITY_SQL = """
CREATE TABLE Student  (sid INTEGER PRIMARY KEY, name TEXT, age INTEGER, major TEXT);
CREATE TABLE Course   (cid TEXT PRIMARY KEY, title TEXT, dept TEXT, credits INTEGER);
CREATE TABLE Enrolled (sid INTEGER, cid TEXT, grade TEXT);
CREATE TABLE Lecturer (lid TEXT PRIMARY KEY, name TEXT, dept TEXT);
CREATE TABLE Teaches  (lid TEXT, cid TEXT);

INSERT INTO Student VALUES
  (1,'Alice',22,'CS'), (2,'Bob',19,'Math'), (3,'Chen Wei',21,'CS'), (4,'Priya',23,'Physics'),
  (5,'Omar',20,'CS'), (6,'Lena',24,'Math'), (7,'Zoe',18,'Physics');
INSERT INTO Course VALUES
  ('C1','Databases','CS',4), ('C2','Algorithms','CS',4),
  ('C3','Calculus','Math',3), ('C4','Mechanics','Physics',3);
INSERT INTO Enrolled VALUES
  (1,'C1','A'), (1,'C2','B'), (2,'C3','A'), (3,'C1','B'), (3,'C2','A'),
  (4,'C4','B'), (4,'C1','C'), (6,'C3','B'), (5,'C1','A');
INSERT INTO Lecturer VALUES ('L1','Tan','CS'), ('L2','Lim','Math'), ('L3','Ng','CS');
INSERT INTO Teaches VALUES ('L1','C1'), ('L3','C2'), ('L2','C3'), ('L1','C4');
"""


def build_university_db(path: str) -> str:
    conn = sqlite3.connect(path)
    conn.executescript(UNIVERSITY_SQL)
    conn.close()
    return path
