"""SC2207 Tutorial 5.5 as RA questions, plus one lecture example with data.

The model answers are the tutorial's own (solution slides, from Ong Chin Ann), adjusted
only where the slides disagree with the question sheet, which is followed:
  * Q1(iii): the sheet says ‘Database System’, the slides ‘Database Systems’.
  * Q2: the sheet names the table RESERVATIONS, the slides RESERVATION.
Primary keys are our reading of the (underlined) keys in the handout. Q3's assumption
"teamid-one is always smaller than teamid-two" is a CHECK constraint, so generated
test data respects it. The tutorial questions have no data, like the tutorial.

Used by scripts/seed_ra_local.py.
"""

UNIVERSITY = """CREATE TABLE STUDENT (Sid INTEGER PRIMARY KEY, Sname TEXT, Sex TEXT, Age INTEGER, Year INTEGER, GPA REAL);
CREATE TABLE DEPT (Dname TEXT PRIMARY KEY, Numphds INTEGER);
CREATE TABLE PROF (Pname TEXT PRIMARY KEY, Dname TEXT);
CREATE TABLE COURSE (Cno INTEGER, Cname TEXT, Dname TEXT, PRIMARY KEY (Cno, Dname));
CREATE TABLE MAJOR (Dname TEXT, Sid INTEGER, PRIMARY KEY (Dname, Sid));
CREATE TABLE SECTION (Dname TEXT, Cno INTEGER, Sectno INTEGER, Pname TEXT, PRIMARY KEY (Dname, Cno, Sectno));
CREATE TABLE ENROLL (Sid INTEGER, Grade REAL, Dname TEXT, Cno INTEGER, Sectno INTEGER, PRIMARY KEY (Sid, Dname, Cno, Sectno));"""

RAILWAY = """CREATE TABLE TRAINS (train_num INTEGER PRIMARY KEY, source_city TEXT, destination_city TEXT);
CREATE TABLE DEPARTURES (train_num INTEGER REFERENCES TRAINS(train_num), date TEXT, train_type TEXT,
  PRIMARY KEY (train_num, date));
CREATE TABLE PASSENGERS (passenger_ssn INTEGER PRIMARY KEY, passenger_name TEXT, address TEXT);
CREATE TABLE RESERVATIONS (passenger_ssn INTEGER REFERENCES PASSENGERS(passenger_ssn),
  train_num INTEGER REFERENCES TRAINS(train_num), date TEXT, seat_number INTEGER,
  PRIMARY KEY (passenger_ssn, train_num, date));"""

SOCCER = """CREATE TABLE Teams (name TEXT, groupname TEXT, teamid INTEGER PRIMARY KEY);
CREATE TABLE Players (name TEXT, teamid INTEGER, matches INTEGER, numgoals INTEGER);
CREATE TABLE Results ("teamid-one" INTEGER, "teamid-two" INTEGER, scoreone INTEGER, scoretwo INTEGER,
  matchdate TEXT, PRIMARY KEY ("teamid-one", "teamid-two", matchdate),
  CHECK ("teamid-one" < "teamid-two"));"""

_SCHEMA_NOTE = "\n\nThe database has no data: your answer is checked on many generated databases."

QUESTIONS = [
    {"title": "Tutorial 5.5 Q1(i) — professors in small departments", "difficulty": "easy",
     "description": "Find the names of professors who work in departments that have fewer than 50 PhD students."
                    + _SCHEMA_NOTE,
     "schema_sql": UNIVERSITY,
     "model_answer": "R1 := σ Numphds < 50 (DEPT)\nAnswer := π Pname (PROF ⋈ R1)"},
    {"title": "Tutorial 5.5 Q1(ii) — lowest GPA", "difficulty": "medium",
     "description": "Find the name(s) of student(s) with the lowest GPA." + _SCHEMA_NOTE,
     "schema_sql": UNIVERSITY,
     "model_answer": "R1 := γ MIN(GPA)→MinGPA (STUDENT)\nR2 := STUDENT ⋈ STUDENT.GPA=R1.MinGPA R1\n"
                     "Answer := π Sname (R2)"},
    {"title": "Tutorial 5.5 Q1(iii) — took ‘Database System’", "difficulty": "medium",
     "description": "Find the names and majors of students who have taken the ‘Database System’ course."
                    + _SCHEMA_NOTE,
     "schema_sql": UNIVERSITY,
     "model_answer": "R1 := π Dname, Cno (σ Cname=‘Database System’ COURSE)\nR2 := π Sid (R1 ⋈ ENROLL)\n"
                     "Answer := π Sname, Dname (R2 ⋈ MAJOR ⋈ STUDENT)"},
    {"title": "Tutorial 5.5 Q1(iv) — all Civil Engineering courses", "difficulty": "hard",
     "description": "Find the ids, names, and GPAs of the students who have taken all courses from the "
                    "‘Civil Engineering’ department." + _SCHEMA_NOTE,
     "schema_sql": UNIVERSITY,
     "model_answer": "R1 := π Dname, Cno (σ Dname = ‘Civil Engineering’ COURSE)\nR2 := π Sid, Dname, Cno ENROLL\n"
                     "R3 := R2 ÷ R1\nAnswer := π Sid, Sname, GPA (R3 ⋈ STUDENT)"},
    {"title": "Tutorial 5.5 Q2(i) — trains to Minneapolis and San Francisco", "difficulty": "easy",
     "description": "Find the cities that have direct (non-stop) trains to both Minneapolis and San Francisco."
                    + _SCHEMA_NOTE,
     "schema_sql": RAILWAY,
     "model_answer": "π source_city ( σ destination_city = “Minneapolis” (TRAINS)) ∩ "
                     "π source_city ( σ destination_city = “San Francisco” (TRAINS))"},
    {"title": "Tutorial 5.5 Q2(ii) — trains without reservations", "difficulty": "easy",
     "description": "Find the train_num and date of all trains for which there are no reservations." + _SCHEMA_NOTE,
     "schema_sql": RAILWAY,
     "model_answer": "π train_num, date (DEPARTURES) - π train_num, date ( RESERVATIONS)"},
    {"title": "Tutorial 5.5 Q3(i) — pairs whose matches all ended in a tie", "difficulty": "medium",
     "description": "List all the pairs of teamids such that all the matches between each pair of teams ended in "
                    "a tie. You can assume that teamid-one is always smaller than teamid-two." + _SCHEMA_NOTE,
     "schema_sql": SOCCER,
     "model_answer": "R1 := π teamid-one, teamid-two (σ scoreone > scoretwo (Results))  // team one won\n"
                     "R2 := π teamid-one, teamid-two (σ scoreone < scoretwo (Results))  // team two won\n"
                     "R3 := R1 ∪ R2  // these are all the winners\n"
                     "R4 := π teamid-one, teamid-two ((Results))  // all teams\nAnswer := R4 - R3"},
    {"title": "Tutorial 5.5 Q3(ii) — teams that lost every game", "difficulty": "hard",
     "description": "Find the names (not the teamids) of the teams that lost every game they played." + _SCHEMA_NOTE,
     "schema_sql": SOCCER,
     "model_answer": "R1 := ρ s1(teamid)(π teamid-one (σ scoreone >= scoretwo (Results)))\n"
                     "R2 := ρ s2(teamid)(π teamid-two (σ scoreone <= scoretwo (Results)))\n"
                     "temp1 := R1 ∪ R2\ntemp2 := π teamid (Teams) - temp1\nresult := π name (Teams ⋈ temp2)"},
    {"title": "Tutorial 5.5 Q4 — maximum without aggregation", "difficulty": "medium",
     "description": "Give a relational algebra expression to find the maximum value in the relation R(A) "
                    "without using aggregate operations." + _SCHEMA_NOTE,
     "schema_sql": "CREATE TABLE R (A INTEGER);",
     "model_answer": "S := R\nR1 := σ R.A < S.A (R × S)\nAnswer := R – π R.A (R1)"},
    {"title": "Tutorial 5.5 Q5 — top 2 values", "difficulty": "hard",
     "description": "Given R(a, b) and S(b, c), where a, b, c are integers, find the top 2 values of a present in R."
                    + _SCHEMA_NOTE,
     "schema_sql": "CREATE TABLE R (a INTEGER, b INTEGER);\nCREATE TABLE S (b INTEGER, c INTEGER);",
     "model_answer": "Temp1 := (R × ρR1 (R) × ρR2 (R))\n"
                     "Temp2 := σ R1.a > R.a AND R2.a > R1.a (Temp1)  // the 3rd value and onwards\n"
                     "Answer := π a (R) – π R.a (Temp2)"},
    {"title": "Lecture 2 — highest Quiz 1 score", "difficulty": "easy",
     "description": "Find the name(s) of the student(s) with the highest score in Quiz1 "
                    "(lecture 2, “student with the highest score”). This question has data: you can see it below.",
     "schema_sql": "CREATE TABLE Quiz1 (Name TEXT PRIMARY KEY, Score INTEGER);",
     "data_sql": "INSERT INTO Quiz1 VALUES ('Alice', 70), ('Bob', 90), ('Cathy', 80), ('David', 100);",
     "model_answer": "R1 := γ MAX(Score)→MaxScore(Quiz1)\nR2 := Quiz1 ⋈ Score = MaxScore R1\nR3 := Π Name(R2)"},
]
