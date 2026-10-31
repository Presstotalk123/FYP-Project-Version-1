"""Rebuild the reviewed-in-UI starter manifest from checked-in source exercises.

This generates *draft* oracle suggestions, never approved/published content.
Run from the repository root after installing backend requirements.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.competition_executor import execute
from app.services.incident_authoring import normalise_source, mutate


def incident(title, schema, seeds, reference, faulty, table, difficulty, cause, template):
    summary = f'SELECT COUNT(*) AS records FROM "{table}"'
    components = [
        {"id": "report", "label": "Application report", "purpose": "Feeds the affected report in the application.", "query": faulty, "reference_query": reference},
        {"id": "records", "label": "Record summary", "purpose": "Shows how many primary records are registered.", "query": summary, "reference_query": summary},
    ]
    scenarios = []
    for index, seed in enumerate(seeds):
        outputs = {}
        for c in components:
            result = execute(schema, seed, c["reference_query"])
            if not result["success"]:
                raise ValueError(result["error"])
            outputs[c["id"]] = {"columns": result["columns"], "rows": result["rows"]}
        scenarios.append({"id": ("visible", "boundary", "empty")[index], "label": ("Initial incident records", "Boundary and cardinality records", "Empty relations")[index], "visible": index == 0, "seed_sql": seed, "approved_outputs": outputs})
    return {"title": title, "topic": "joins", "difficulty": difficulty, "complaint": "Instructor: replace this complaint before approval.",
            "business_rules": "Instructor: confirm the application inclusion and multiplicity rules before approval.",
            "schema_sql": schema, "components": components, "culprit_component": "report", "fault_template": template,
            "fault_cause": cause, "checkpoints": ["Compare the primary records with the report output.", "Trace which relationships include, omit or multiply records.", cause],
            "scenarios": scenarios, "oracle_confirmed": False, "alternative_repairs": [reference]}


def build():
    root = Path(__file__).resolve().parents[2]
    bank = {str(r["id"]): r for name in ("leetcode_questions.json", "uncovered_leetcode_questions.json") for r in json.loads((root / name).read_text(encoding="utf-8"))}
    definitions = [
        ("175", "Missing directory entries", "easy", None, "left_to_inner", "Person",
         "INSERT INTO Person VALUES (10,'Kai','Tan'),(20,'Kai','Tan'); INSERT INTO Address VALUES (1,10,NULL,'North'),(2,20,'East','East'),(3,20,'East','East');",
         "A registered person disappeared from our people-and-address directory.",
         "The directory must display every person. Include one row for each matching address and NULL address fields when there is no match. Repeated names and address values are valid."),
        ("183", "Outreach recipients look wrong", "easy", "SELECT c.name AS Customers FROM Customers c WHERE NOT EXISTS (SELECT 1 FROM Orders o WHERE o.customerId=c.id)", "invert_exists", "Customers",
         "INSERT INTO Customers VALUES (10,'Dee'),(20,'Eli'); INSERT INTO Orders VALUES (1,10),(2,10),(3,20);",
         "Our outreach list includes regular buyers and misses people who have never ordered.",
         "Show each customer with no order. A customer with one or several orders must be absent. Customers are identified by their ID, not their name."),
        ("181", "Payroll alerts reach the wrong staff", "medium", None, "reverse_comparison", "Employee",
         "INSERT INTO Employee VALUES (10,'Lead',90000,NULL),(20,'Peer',90000,10),(30,'Junior',80000,10);",
         "Payroll alerts are being sent for the wrong reporting relationships.",
         "An alert belongs to an employee only when their salary is strictly greater than their own manager's salary. Equal salaries and staff without a manager do not trigger alerts."),
        ("1378", "Identity badges are mismatched", "medium", None, "wrong_join_key", "Employees",
         "INSERT INTO Employees VALUES (2,'Noor'),(3,'Uma'); INSERT INTO EmployeeUNI VALUES (2,100),(3,200);",
         "The staff directory assigns a badge to the wrong employee and loses other badge mappings.",
         "Display every employee's name and their mapped unique_id, or NULL when no mapping exists. Employees.id and EmployeeUNI.id identify the same employee; unique_id is a badge identifier."),
        ("1581", "Unconverted visits vanish", "hard", None, "left_to_inner", "Visits",
         "INSERT INTO Visits VALUES (10,100),(11,100),(12,200); INSERT INTO Transactions VALUES (1,12,50),(2,12,60);",
         "The customer dashboard reports no visits without purchases, despite recorded visits with no transaction.",
         "For each customer with at least one visit that has no transaction, report customer_id and count_no_trans. Count visits without transactions, not transaction records; one visit can have multiple transactions."),
        ("1068", "Revenue is attributed incorrectly", "hard", "SELECT p.product_name, SUM(s.quantity*s.price) AS revenue FROM Sales s INNER JOIN Product p ON s.product_id=p.product_id GROUP BY p.product_id,p.product_name", "wrong_join_key", "Sales",
         "INSERT INTO Sales VALUES (1,1,2024,2,10),(2,1,2025,3,20); INSERT INTO Product VALUES (1,'Desk'),(2,'Lamp');",
         "The sales dashboard shows missing revenue or attributes it to an unrelated product.",
         "Report total quantity times price for each product with sales, grouping by product identity and name. Sales.product_id references Product.product_id; sale_id identifies a sale, not a product."),
    ]
    rows = []
    for external_id, title, difficulty, override, template, table, boundary, complaint, rules in definitions:
        raw = bank[external_id]
        snapshot, diagnostics = normalise_source(raw)
        if not snapshot["eligible"]:
            raise ValueError(diagnostics)
        reference = override or snapshot["reference_query"]
        if template in {"left_to_inner", "invert_exists"}:
            faulty = mutate(reference, template)
        elif template == "reverse_comparison":
            from sqlglot import exp
            from app.core.competition_executor import parse_select
            tree = parse_select(reference).copy(); target = tree.find(exp.GT)
            target.replace(exp.LT(this=target.this.copy(), expression=target.expression.copy())); faulty = tree.sql(dialect="sqlite")
        elif external_id == "1378":
            faulty = reference.replace("e.id = eu.id", "e.id = eu.unique_id")
            if faulty == reference: raise ValueError("Review source formatting before regenerating the wrong-key template")
        else:
            faulty = reference.replace("s.product_id=p.product_id", "s.sale_id=p.product_id")
        doc = incident(title, snapshot["schema_sql"], [snapshot["seed_sql"], boundary, ""], reference, faulty, table, difficulty,
                       {"left_to_inner": "An INNER JOIN removes unmatched records required by this report.", "invert_exists": "The existence predicate selects customers with orders instead of customers without orders.", "reverse_comparison": "The salary comparison is reversed; an employee must earn more than their own manager.", "wrong_join_key": "The join uses a different identifier domain, creating false matches or missing relationships."}[template], template + ":v1")
        doc["complaint"], doc["business_rules"] = complaint, rules
        source = {k: raw[k] for k in ("id", "title", "sql_schema", "answer")}
        rows.append({"key": "leetcode-" + external_id, "source": source, "document": doc})
    output = root / "backend/app/data/database_rescue_pilot.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Prepared {len(rows)} unapproved starter definitions in {output}")


if __name__ == "__main__":
    build()
