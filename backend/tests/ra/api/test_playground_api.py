"""The RA Playground API: switched off by default, needs sign-in, reports errors by source."""
from app.services.ra.examples import EXAMPLES

QUIZ = {"schema_sql": "CREATE TABLE Quiz1 (Name TEXT PRIMARY KEY, Score INTEGER);",
        "data_sql": "INSERT INTO Quiz1 VALUES ('Alice', 70), ('Bob', 90);"}


def test_status_is_public_and_off_by_default(client):
    r = client.get("/api/v1/ra/status")
    assert r.status_code == 200 and r.json() == {"enabled": False, "aggregate_nulls": "sql"}


def test_everything_else_404s_while_off(client, student_headers):
    assert client.post("/api/v1/ra/playground/run", json=QUIZ, headers=student_headers).status_code == 404
    assert client.get("/api/v1/ra/playground/examples", headers=student_headers).status_code == 404


def test_sign_in_is_required(client, ra_on):
    assert client.post("/api/v1/ra/playground/run", json=QUIZ).status_code == 401


def test_run_returns_result_and_steps(client, student_headers, ra_on):
    r = client.post("/api/v1/ra/playground/run", headers=student_headers,
                    json={**QUIZ, "expression": "R1 := σ Score > 80 Quiz1\nΠ Name R1"}).json()
    assert r["ok"] and r["result"]["columns"] == ["Name"] and r["result"]["rows"] == [["Bob"]]
    assert [s["name"] for s in r["result"]["steps"]] == ["R1", None]
    assert r["relations"][0]["name"] == "Quiz1" and r["relations"][0]["primary_key"] == ["Name"]


def test_empty_expression_only_loads_the_schema(client, student_headers, ra_on):
    r = client.post("/api/v1/ra/playground/run", headers=student_headers, json=QUIZ).json()
    assert r["ok"] and r["result"] is None and len(r["relations"][0]["rows"]) == 2


def test_errors_say_which_input_is_wrong(client, student_headers, ra_on):
    bad_schema = client.post("/api/v1/ra/playground/run", headers=student_headers,
                             json={"schema_sql": "CREATE TABL Quiz1 (x INT);", "expression": "Quiz1"}).json()
    assert not bad_schema["ok"] and bad_schema["error_source"] == "schema" and bad_schema["error"]["code"] == "RA020"
    bad_expr = client.post("/api/v1/ra/playground/run", headers=student_headers,
                           json={**QUIZ, "expression": "σ Grade > 1 Quiz1"}).json()
    assert bad_expr["error_source"] == "expression" and bad_expr["error"]["code"] == "RA003"
    assert bad_expr["error"]["line"] == 1 and bad_expr["relations"]


def test_examples_all_run(client, student_headers, ra_on):
    examples = client.get("/api/v1/ra/playground/examples", headers=student_headers).json()
    assert [e["id"] for e in examples] == [e["id"] for e in EXAMPLES]
    for ex in examples:
        for expression in ex["expressions"]:
            r = client.post("/api/v1/ra/playground/run", headers=student_headers,
                            json={"schema_sql": ex["schema_sql"], "data_sql": ex["data_sql"],
                                  "expression": expression}).json()
            assert r["ok"], (ex["id"], expression, r["error"])


def test_oversized_input_is_refused(client, student_headers, ra_on):
    r = client.post("/api/v1/ra/playground/run", headers=student_headers,
                    json={**QUIZ, "expression": "x" * 6000})
    assert r.status_code == 422
