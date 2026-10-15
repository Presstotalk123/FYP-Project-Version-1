"""Regression tests pinning the behaviour of SQL and Graph labs.

Written against the inherited code *before* the lab-engine registry refactor, so the
same suite proves the refactor changed nothing. Each test walks one lab type through
every place labs.py used to branch on ``lab_type``: create, update (template
regeneration), schema preview, session start, execute, database state, task answer
assignment, order-sensitivity toggle, and task validation.
"""
import os

import pytest

SQL_SCHEMA = "CREATE TABLE fruit (id INTEGER PRIMARY KEY, name TEXT, price REAL);"
SQL_SEED = "INSERT INTO fruit VALUES (1,'apple',1.5),(2,'banana',0.5),(3,'cherry',3.0);"

GRAPH_CYPHER = (
    "CREATE (:Person {name: 'Alice', age: 30});"
    "CREATE (:Person {name: 'Bob', age: 25});"
    "CREATE (:Person {name: 'Cara', age: 41})"
)

CASES = {
    "sql": {
        "schema": SQL_SCHEMA,
        "seed": SQL_SEED,
        "answer": "SELECT name FROM fruit WHERE price > 1 ORDER BY name",
        "wrong": "SELECT name FROM fruit",
        "mutation": "INSERT INTO fruit VALUES (4,'durian',9.0)",
        "count": "SELECT COUNT(*) AS n FROM fruit",
    },
    "graph": {
        "schema": GRAPH_CYPHER,
        "seed": " ",  # the lab form sends a placeholder for graph labs
        "answer": "MATCH (p:Person) WHERE p.age > 28 RETURN p.name AS name ORDER BY name",
        "wrong": "MATCH (p:Person) RETURN p.name AS name",
        "mutation": "CREATE (:Person {name: 'Dev', age: 35})",
        "count": "MATCH (p:Person) RETURN count(p) AS n",
    },
}


def _create_lab(client, headers, lab_type):
    case = CASES[lab_type]
    r = client.post("/api/v1/labs", headers=headers, json={
        "title": f"{lab_type} regression lab", "description": "pinned behaviour",
        "schema_sql": case["schema"], "sample_data_sql": case["seed"], "lab_type": lab_type,
    })
    assert r.status_code == 201, r.text
    assert r.json()["lab_type"] == lab_type
    return r.json()["id"]


def _count(client, headers, session_id, lab_type):
    r = client.post(f"/api/v1/labs/session/{session_id}/execute", headers=headers,
                    json={"query": CASES[lab_type]["count"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"], body
    return list(body["results"][0].values())[0]


@pytest.mark.parametrize("lab_type", ["sql", "graph"])
def test_full_lab_lifecycle(client, staff_headers, lab_type):
    from app.utils.lab_db_manager import get_lab_template_path

    case = CASES[lab_type]
    lab_id = _create_lab(client, staff_headers, lab_type)
    assert os.path.exists(get_lab_template_path(lab_id))

    # Schema preview reads the template through the type-specific reader.
    r = client.get(f"/api/v1/labs/{lab_id}/preview/schema", headers=staff_headers)
    assert r.status_code == 200, r.text
    assert len(r.json()["tables"]) >= 1

    # Task + reference answer (hash computed on the template by the type's executor).
    r = client.post(f"/api/v1/labs/{lab_id}/tasks", headers=staff_headers,
                    json={"title": "T1", "description": "older than / pricier than"})
    assert r.status_code == 201, r.text
    task_id = r.json()["id"]
    r = client.post(f"/api/v1/labs/{lab_id}/tasks/{task_id}/assign", headers=staff_headers,
                    json={"query": case["answer"]})
    assert r.status_code == 200, r.text
    assert r.json()["has_answer"] is True

    # Toggling order sensitivity on an answered task recomputes the hash via the executor.
    r = client.put(f"/api/v1/labs/{lab_id}/tasks/{task_id}", headers=staff_headers,
                   json={"order_sensitive": True})
    assert r.status_code == 200, r.text
    assert r.json()["order_sensitive"] is True

    # Session: private copy of the template.
    r = client.post(f"/api/v1/labs/{lab_id}/session/start", headers=staff_headers)
    assert r.status_code == 200, r.text
    session_id = r.json()["session_id"]

    # Execute dispatches to the type's executor; mutations only touch the private copy.
    before = _count(client, staff_headers, session_id, lab_type)
    r = client.post(f"/api/v1/labs/session/{session_id}/execute", headers=staff_headers,
                    json={"query": case["mutation"]})
    assert r.status_code == 200 and r.json()["success"], r.text
    assert _count(client, staff_headers, session_id, lab_type) == before + 1

    # Database-state view uses the type's reader.
    r = client.get(f"/api/v1/labs/session/{session_id}/database", headers=staff_headers)
    assert r.status_code == 200, r.text
    assert "tables" in r.json()

    # Validation runs the student's query on their session copy with the type's executor.
    r = client.post("/api/v1/labs/tasks/validate", headers=staff_headers,
                    json={"task_id": task_id, "session_id": session_id, "user_query": case["wrong"]})
    assert r.status_code == 200 and r.json()["is_correct"] is False, r.text

    # Updating the schema regenerates the template with the type's builder.
    r = client.put(f"/api/v1/labs/{lab_id}", headers=staff_headers,
                   json={"schema_sql": case["schema"], "sample_data_sql": case["seed"] if lab_type == "sql" else "  "})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("lab_type", ["sql", "graph"])
def test_correct_answer_validates(client, staff_headers, lab_type):
    case = CASES[lab_type]
    lab_id = _create_lab(client, staff_headers, lab_type)
    task_id = client.post(f"/api/v1/labs/{lab_id}/tasks", headers=staff_headers,
                          json={"title": "T", "description": "d"}).json()["id"]
    client.post(f"/api/v1/labs/{lab_id}/tasks/{task_id}/assign", headers=staff_headers,
                json={"query": case["answer"]})
    session_id = client.post(f"/api/v1/labs/{lab_id}/session/start",
                             headers=staff_headers).json()["session_id"]
    r = client.post("/api/v1/labs/tasks/validate", headers=staff_headers,
                    json={"task_id": task_id, "session_id": session_id, "user_query": case["answer"]})
    assert r.status_code == 200, r.text
    assert r.json()["is_correct"] is True


def test_invalid_lab_type_rejected(client, staff_headers):
    r = client.post("/api/v1/labs", headers=staff_headers, json={
        "title": "x", "description": "x", "schema_sql": SQL_SCHEMA,
        "sample_data_sql": SQL_SEED, "lab_type": "vector",
    })
    assert r.status_code == 422
