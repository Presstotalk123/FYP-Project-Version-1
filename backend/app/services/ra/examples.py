"""Ready-made schemas for the RA Playground.

The lecture examples use the data printed on the CZ2007/SC2207 Topic 5 slides, so a
student can reproduce a slide's result exactly. The Tutorial 5.5 schemas come with no
data in the tutorial; the rows here are made up for practice and say so. Primary keys
in the tutorial schemas are our reading of the (underlined) keys in the handout.
"""

LECTURE_1 = {
    "id": "lecture-1",
    "title": "Lecture 1 — Students, Grades, CrsSch",
    "description": "σ, Π, ∪, ∩, −, ⋈ and × on the data from lecture 1.",
    "schema_sql": """CREATE TABLE Students (ID INTEGER PRIMARY KEY, Name TEXT, Age INTEGER, School TEXT);
CREATE TABLE Grades (Name TEXT, Course TEXT, Grade TEXT, PRIMARY KEY (Name, Course));
CREATE TABLE CrsSch (Course TEXT PRIMARY KEY, School TEXT);""",
    "data_sql": """INSERT INTO Students VALUES (1234, 'Alice', 20, 'SCSE'), (5678, 'Bob', 20, 'EEE'),
  (3742, 'Cathy', 22, 'SCSE'), (9413, 'David', 21, 'CEE');
INSERT INTO Grades VALUES ('Alice', 'DB', 'A'), ('Alice', 'DM', 'C'), ('Bob', 'DB', 'B'),
  ('Bob', 'NN', 'B'), ('Cathy', 'SP', 'B'), ('Cathy', 'NN', 'A');
INSERT INTO CrsSch VALUES ('DB', 'SCSE'), ('DM', 'SCSE'), ('AI', 'SCSE'), ('NN', 'EEE'), ('SP', 'EEE');""",
    "expressions": [
        "Π ID, Name (σ School = 'SCSE' Students)",
        "Π Name Grades",
        "(Π Name Grades) − (Π Name σ Course = 'DM' Grades)",
        "Π Name (Grades ⋈ σ School = 'SCSE' CrsSch) − Π Name (Grades ⋈ σ School = 'EEE' CrsSch)",
    ],
}

LECTURE_2 = {
    "id": "lecture-2",
    "title": "Lecture 2 — Quiz1, Quiz2, Quiz3",
    "description": "θ-joins, assignment, ρ, δ and γ on the quiz scores from lecture 2.",
    "schema_sql": """CREATE TABLE Quiz1 (Name TEXT PRIMARY KEY, Score INTEGER);
CREATE TABLE Quiz2 (Name TEXT PRIMARY KEY, Score INTEGER);
CREATE TABLE Quiz3 (Name TEXT PRIMARY KEY, Score INTEGER);""",
    "data_sql": """INSERT INTO Quiz1 VALUES ('Alice', 70), ('Bob', 90), ('Cathy', 80), ('David', 100);
INSERT INTO Quiz2 VALUES ('Alice', 80), ('Bob', 90), ('Cathy', 90), ('David', 70);
INSERT INTO Quiz3 VALUES ('Alice', 90), ('Bob', 90), ('Cathy', 80), ('David', 70);""",
    "expressions": [
        "Quiz1 ⋈ Quiz1.Name = Quiz2.Name AND Quiz1.Score < Quiz2.Score Quiz2",
        "R1 := Quiz1\nR2 := Quiz1 ⋈ Quiz1.Name <> R1.Name AND Quiz1.Score < R1.Score R1\nR3 := Π Quiz1.Name R2\nR4 := Π Name Quiz1 − R3",
        "R1 := γ MAX(Score) → MaxScore (Quiz1)\nR2 := Quiz1 ⋈ Score = MaxScore R1\nΠ Name R2",
    ],
}

LECTURE_3 = {
    "id": "lecture-3",
    "title": "Lecture 3 — division and outer joins",
    "description": "÷ on Owns/AppleP, outer joins on Students/Donations, and the male-stars example.",
    "schema_sql": """CREATE TABLE Owns (Name TEXT, Product TEXT, PRIMARY KEY (Name, Product));
CREATE TABLE AppleP (Product TEXT PRIMARY KEY, Price INTEGER);
CREATE TABLE Students (Name TEXT PRIMARY KEY, School TEXT);
CREATE TABLE Donations (Name TEXT PRIMARY KEY, Amount INTEGER);
CREATE TABLE CastIn (Name TEXT, Movie TEXT, Year INTEGER, PRIMARY KEY (Name, Movie));
CREATE TABLE Stars (Name TEXT PRIMARY KEY, Gender TEXT, Birth INTEGER);""",
    "data_sql": """INSERT INTO Owns VALUES ('Alice', 'iPad'), ('Alice', 'iPhone'), ('Bob', 'iPhone'), ('Cathy', 'iPad');
INSERT INTO AppleP VALUES ('iPhone', 999), ('iPad', 699);
INSERT INTO Students VALUES ('Alice', 'SCSE'), ('Bob', 'EEE'), ('Cathy', 'CEE'), ('David', 'SCSE');
INSERT INTO Donations VALUES ('Cathy', 100), ('David', 200), ('Eddie', 300), ('Fred', 400);
INSERT INTO CastIn VALUES ('John', 'Batman', 2012), ('Steve', 'Batman', 2012), ('Meg', 'The Women', 2008);
INSERT INTO Stars VALUES ('John', 'Male', 1980), ('Meg', 'Female', 1981), ('Steve', 'Male', 1990);""",
    "expressions": [
        "Owns ÷ (Π Product AppleP)",
        "Students ⟕ Donations",
        "R1 := σ Gender = 'Male' Stars\nR2 := CastIn ⟕ R1\nγ Movie, COUNT(Gender) → MaleStars (R2)",
    ],
}

TUTORIAL_Q1 = {
    "id": "tutorial-5-5-q1",
    "title": "Tutorial 5.5 Q1 — university (made-up data)",
    "description": "The Q1 schema with small made-up data: two students tie for the lowest GPA, "
                   "and only one has taken every Civil Engineering course.",
    "schema_sql": """CREATE TABLE STUDENT (Sid INTEGER PRIMARY KEY, Sname TEXT, Sex TEXT, Age INTEGER, Year INTEGER, GPA REAL);
CREATE TABLE DEPT (Dname TEXT PRIMARY KEY, Numphds INTEGER);
CREATE TABLE PROF (Pname TEXT PRIMARY KEY, Dname TEXT);
CREATE TABLE COURSE (Cno INTEGER, Cname TEXT, Dname TEXT, PRIMARY KEY (Cno, Dname));
CREATE TABLE MAJOR (Dname TEXT, Sid INTEGER, PRIMARY KEY (Dname, Sid));
CREATE TABLE SECTION (Dname TEXT, Cno INTEGER, Sectno INTEGER, Pname TEXT, PRIMARY KEY (Dname, Cno, Sectno));
CREATE TABLE ENROLL (Sid INTEGER, Grade REAL, Dname TEXT, Cno INTEGER, Sectno INTEGER, PRIMARY KEY (Sid, Dname, Cno, Sectno));""",
    "data_sql": """INSERT INTO STUDENT VALUES (1, 'Ann', 'F', 21, 3, 3.6), (2, 'Ben', 'M', 22, 4, 2.4),
  (3, 'Cal', 'M', 20, 2, 3.1), (4, 'Dee', 'F', 23, 4, 2.4);
INSERT INTO DEPT VALUES ('Civil Engineering', 30), ('Computer Science', 80), ('Mathematics', 45);
INSERT INTO PROF VALUES ('Prof Lee', 'Civil Engineering'), ('Prof Ng', 'Computer Science'), ('Prof Tan', 'Mathematics');
INSERT INTO COURSE VALUES (101, 'Statics', 'Civil Engineering'), (102, 'Surveying', 'Civil Engineering'),
  (201, 'Database System', 'Computer Science'), (301, 'Calculus', 'Mathematics');
INSERT INTO MAJOR VALUES ('Civil Engineering', 1), ('Computer Science', 2), ('Computer Science', 3), ('Mathematics', 4);
INSERT INTO SECTION VALUES ('Civil Engineering', 101, 1, 'Prof Lee'), ('Civil Engineering', 102, 1, 'Prof Lee'),
  ('Computer Science', 201, 1, 'Prof Ng'), ('Mathematics', 301, 1, 'Prof Tan');
INSERT INTO ENROLL VALUES (1, 3.5, 'Civil Engineering', 101, 1), (1, 3.7, 'Civil Engineering', 102, 1),
  (1, 3.2, 'Computer Science', 201, 1), (2, 2.1, 'Civil Engineering', 101, 1),
  (3, 3.0, 'Computer Science', 201, 1), (4, 2.5, 'Mathematics', 301, 1);""",
    "expressions": [
        "Π Pname (PROF ⋈ σ Numphds < 50 DEPT)",
        "R1 := γ MIN(GPA) → MinGPA (STUDENT)\nR2 := STUDENT ⋈ GPA = MinGPA R1\nΠ Sname R2",
        "R1 := Π Cno, Dname σ Dname = 'Civil Engineering' COURSE\nR2 := Π Sid, Cno, Dname ENROLL\nR3 := R2 ÷ R1\nΠ Sid, Sname, GPA (R3 ⋈ STUDENT)",
    ],
}

TUTORIAL_Q2 = {
    "id": "tutorial-5-5-q2",
    "title": "Tutorial 5.5 Q2 — railway (made-up data)",
    "description": "The Q2 railway schema with small made-up data.",
    "schema_sql": """CREATE TABLE TRAINS (train_num INTEGER PRIMARY KEY, source_city TEXT, destination_city TEXT);
CREATE TABLE DEPARTURES (train_num INTEGER, date TEXT, train_type TEXT, PRIMARY KEY (train_num, date));
CREATE TABLE PASSENGERS (passenger_ssn INTEGER PRIMARY KEY, passenger_name TEXT, address TEXT);
CREATE TABLE RESERVATIONS (passenger_ssn INTEGER, train_num INTEGER, date TEXT, seat_number INTEGER,
  PRIMARY KEY (passenger_ssn, train_num, date));""",
    "data_sql": """INSERT INTO TRAINS VALUES (1, 'Chicago', 'Minneapolis'), (2, 'Chicago', 'San Francisco'),
  (3, 'Denver', 'San Francisco'), (4, 'Denver', 'Seattle');
INSERT INTO DEPARTURES VALUES (1, '2026-10-01', 'express'), (2, '2026-10-01', 'local'),
  (3, '2026-10-02', 'express'), (4, '2026-10-02', 'local');
INSERT INTO PASSENGERS VALUES (11, 'Ann', 'Chicago'), (12, 'Ben', 'Denver');
INSERT INTO RESERVATIONS VALUES (11, 1, '2026-10-01', 5), (12, 3, '2026-10-02', 7);""",
    "expressions": [
        "R1 := Π source_city σ destination_city = 'Minneapolis' TRAINS\n"
        "R2 := Π source_city σ destination_city = 'San Francisco' TRAINS\nR1 ∩ R2",
        "(Π train_num, date DEPARTURES) − (Π train_num, date RESERVATIONS)",
    ],
}

EXAMPLES = [LECTURE_1, LECTURE_2, LECTURE_3, TUTORIAL_Q1, TUTORIAL_Q2]
