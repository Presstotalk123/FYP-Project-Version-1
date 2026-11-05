"""Package the Easy/Medium examples from Presentation slides 22.10.26.pptx.

Visible records, queries and answer keys follow slides 5–8. Hidden fixtures and
their explicit outputs exercise equivalent repairs without exposing the keys.
Generated definitions remain drafts; only the disposable demo approves them.
"""
import json
from pathlib import Path


def scenario(name, seed, columns, rows, component, *, visible=False):
    return {"id": name, "label": name.replace("_", " ").title(), "visible": visible,
            "seed_sql": seed, "approved_outputs": {component: {"columns": columns, "rows": rows}}}


def definitions():
    easy_columns = ["student_name", "department_name"]
    easy_reference = """SELECT s.student_name, d.department_name
FROM Students s
JOIN Departments d
  ON s.department_id = d.department_id
ORDER BY s.student_id;"""
    easy = {
        "title": "Empty student directory", "topic": "joins", "difficulty": "easy", "report_style": "verdict",
        "complaint": "Students are registered, but the directory is empty.",
        "business_rules": "Show every student once with their department, ordered by student_id.",
        "schema_sql": """CREATE TABLE Departments (
  department_id INTEGER PRIMARY KEY, department_name TEXT NOT NULL
);
CREATE TABLE Students (
  student_id INTEGER PRIMARY KEY, student_name TEXT NOT NULL,
  department_id INTEGER NOT NULL REFERENCES Departments(department_id)
);""",
        "components": [{"id": "directory", "label": "Student directory", "purpose": "Shows each student's department.",
                        "query": easy_reference.replace("s.department_id =", "s.student_id ="),
                        "reference_query": easy_reference, "order_sensitive": True}],
        "culprit_component": "directory", "fault_template": "wrong_join_key:v1",
        "fault_cause": "Student IDs and department IDs identify different entities. Join the student's department_id to the department's department_id.",
        "checkpoints": ["Compare the Students records with the empty directory output.",
                        "Which column on Students identifies a department?",
                        "Match the foreign key for a student's department to the department's primary key."],
        "scenarios": [
            scenario("visible", "INSERT INTO Departments VALUES (10,'Engineering'),(20,'Business'); INSERT INTO Students VALUES (1,'Alice',20),(2,'Ben',10);",
                     easy_columns, [["Alice", "Business"], ["Ben", "Engineering"]], "directory", visible=True),
            scenario("overlapping_ids", "INSERT INTO Departments VALUES (1,'Science'),(2,'Arts'); INSERT INTO Students VALUES (1,'Dina',2),(2,'Eli',1);",
                     easy_columns, [["Dina", "Arts"], ["Eli", "Science"]], "directory"),
            scenario("shared_department", "INSERT INTO Departments VALUES (7,'Law'),(9,'Design'),(12,'Unused'); INSERT INTO Students VALUES (30,'Same',7),(10,'Same',9),(20,'Noor',7);",
                     easy_columns, [["Same", "Design"], ["Noor", "Law"], ["Same", "Law"]], "directory"),
            scenario("no_students", "INSERT INTO Departments VALUES (10,'Engineering');", easy_columns, [], "directory"),
        ],
        "oracle_confirmed": False, "alternative_repairs": [easy_reference],
    }
    medium_columns = ["resident_id", "resident_name", "open_tickets"]
    medium_query = """SELECT r.resident_id, r.resident_name,
       COUNT(t.ticket_id) AS open_tickets
FROM Residents r
LEFT JOIN Tickets t
  ON r.resident_id = t.resident_id
WHERE t.status = 'OPEN'
GROUP BY r.resident_id, r.resident_name
ORDER BY r.resident_id;"""
    medium_reference = medium_query.replace("\nWHERE t.status = 'OPEN'", "\n AND t.status = 'OPEN'")
    medium = {
        "title": "Missing residents", "topic": "joins", "difficulty": "medium", "report_style": "verdict",
        "complaint": "Some residents are missing from the support dashboard.",
        "business_rules": "Show every resident and their open-ticket count, including zero, ordered by resident_id.",
        "schema_sql": """CREATE TABLE Residents (
  resident_id INTEGER PRIMARY KEY, resident_name TEXT NOT NULL
);
CREATE TABLE Tickets (
  ticket_id INTEGER PRIMARY KEY, resident_id INTEGER NOT NULL REFERENCES Residents(resident_id), status TEXT
);""",
        "components": [{"id": "dashboard", "label": "Support dashboard", "purpose": "Shows residents and the count of their open support tickets.",
                        "query": medium_query, "reference_query": medium_reference, "order_sensitive": True}],
        "culprit_component": "dashboard", "fault_template": "left_join_where:v1",
        "fault_cause": "WHERE removes residents with no open-ticket row. Filter status in the LEFT JOIN's ON clause so every resident remains. COUNT(t.ticket_id) ignores unmatched NULLs and returns zero.",
        "checkpoints": ["Compare the Residents records with the single resident in the dashboard.",
                        "What happens to a LEFT JOIN row when its ticket columns are NULL and WHERE filters status?",
                        "Filter matching tickets in ON and count ticket_id so unmatched residents receive zero."],
        "scenarios": [
            scenario("visible", "INSERT INTO Residents VALUES (1,'Ava'),(2,'Ben'),(3,'Cara'); INSERT INTO Tickets VALUES (101,1,'OPEN'),(102,1,'CLOSED'),(103,3,'CLOSED');",
                     medium_columns, [[1, "Ava", 1], [2, "Ben", 0], [3, "Cara", 0]], "dashboard", visible=True),
            scenario("multiple_tickets", "INSERT INTO Residents VALUES (30,'Same'),(10,'Same'),(20,'Dee'); INSERT INTO Tickets VALUES (201,10,'OPEN'),(202,10,'OPEN'),(203,10,'CLOSED'),(204,20,'CLOSED'),(205,20,NULL);",
                     medium_columns, [[10, "Same", 2], [20, "Dee", 0], [30, "Same", 0]], "dashboard"),
            scenario("no_tickets", "INSERT INTO Residents VALUES (5,'Ivy'),(4,'Hao');", medium_columns, [[4, "Hao", 0], [5, "Ivy", 0]], "dashboard"),
            scenario("no_residents", "", medium_columns, [], "dashboard"),
        ],
        "oracle_confirmed": False, "alternative_repairs": [medium_reference],
    }
    return [{"key": "slides-2026-10-22-" + name, "source": None,
             "provenance": {"file": "Presentation slides 22.10.26.pptx", "slides": slides}, "document": doc}
            for name, slides, doc in (("easy", [5, 6], easy), ("medium", [7, 8], medium))]


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "app/data/database_rescue_slides.json"
    output.write_text(json.dumps(definitions(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Prepared two presentation examples in {output}")
