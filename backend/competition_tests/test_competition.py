import copy
import json
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.config import settings
from app.core.competition_comparator import matches
from app.core.competition_executor import execute, fixture_path
from app.models.competition import Competition, CompetitionDraft, CompetitionIncidentVersion, CompetitionParticipation, CompetitionReward, CompetitionSubmission
from app.services.incident_authoring import adaptation, mutate, normalise_source, validate_document
from conftest import document


def report(client, part, key, *, correct=False, request_key=None):
    base = f"/api/v1/competition-sessions/{part}/items/{key}"
    incident = client.get(base)
    assert incident.status_code == 200, incident.text
    data = incident.json()
    reference = data["components"][0]["query"].replace("INNER JOIN", "LEFT JOIN")
    run = client.post(base + "/runs", json={"query": "SELECT 1 AS evidence"})
    assert run.status_code == 200, run.text
    payload = {"investigation_sql": "SELECT 1 AS evidence", "component_id": "directory", "evidence": "A registered person is absent from the report.",
               "diagnosis": "The join may exclude unmatched records.", "repair_sql": reference if correct else "SELECT 42 AS attempted_repair", "explanation": "I expect unmatched people to appear, but have not yet resolved the query.", "run_id": run.json()["run_id"]}
    saved = client.put(base + "/draft", json={"revision": data["draft"]["revision"], "report": payload})
    assert saved.status_code == 200, saved.text
    body = {"revision": saved.json()["revision"], "request_key": request_key or uuid.uuid4().hex}
    response = client.post(base + "/submissions", json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


def gameplay(client, part):
    data = client.get(f"/api/v1/competition-sessions/{part}/items/gameplay:0")
    assert data.status_code == 200, data.text


def test_complete_participation_with_every_repair_incorrect(published):
    client, session, identity, comp_id, part = published
    gameplay(client, part)
    for index in (2, 0, 1):
        result, _ = report(client, part, f"gameplay:{index}")
        assert result["submitted"] and not result["feedback"]["restored"]
    completed = client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]
    assert completed["participation_complete"] and completed["phase"] == "complete"
    assert completed["points"] == 0 and completed["badges"] == []
    survey = client.post(f"/api/v1/competition-sessions/{part}/survey", json={"usability": 4, "engagement": 4})
    assert survey.status_code == 200


def test_restoration_and_retry_award_exactly_once(published):
    client, session, identity, comp_id, part = published
    gameplay(client, part)
    result, body = report(client, part, "gameplay:0", correct=True)
    assert result["feedback"]["restored"]
    base = f"/api/v1/competition-sessions/{part}/items/gameplay:0"
    again = client.post(base + "/submissions", json=body)
    assert again.json()["id"] == result["id"]
    body["request_key"] = uuid.uuid4().hex
    assert client.post(base + "/submissions", json=body).status_code == 200
    summary = client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]
    assert summary["points"] == 10
    assert session.query(CompetitionReward).filter_by(participation_id=part).count() == 1


def test_missions_open_immediately_and_removed_tests_cannot_be_started(published):
    client, session, identity, comp_id, part = published
    data = client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]
    assert data["phase"] == "gameplay"
    assert len(data["items"]) == 3 and all(i["key"].startswith("gameplay:") for i in data["items"])
    assert "pre_submitted" not in data and "post_submitted" not in data
    assert client.get("/assistance").status_code == 200
    for phase in ("pre_test", "post_test"):
        assert client.post(f"/api/v1/competition-sessions/{part}/phases/{phase}/start").status_code == 422
        assert client.get(f"/api/v1/competition-sessions/{part}/items/{phase}:0").status_code == 404
    base = f"/api/v1/competition-sessions/{part}/items/gameplay:0"
    assert client.post(base + "/submissions", json={"request_key": "empty-report", "revision": 0}).status_code == 400
    assert client.post(f"/api/v1/competition-sessions/{part}/phases/gameplay/submit").status_code == 400
    assert client.post(base + "/help").status_code == 200
    assert client.post(base + "/checks", json={"query": "SELECT 1", "component_id": "directory"}).status_code == 200


def test_private_fields_cross_user_access_and_draft_conflict(published):
    client, session, identity, comp_id, part = published
    gameplay(client, part)
    base = f"/api/v1/competition-sessions/{part}/items/gameplay:0"
    data = client.get(base).json()
    forbidden = {"reference_query", "culprit_component", "fault_cause", "approved_outputs", "scenarios", "source_id", "fault_template"}
    def check(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for v in value.values(): check(v)
        elif isinstance(value, list):
            for v in value: check(v)
    check(data)
    first = client.put(base + "/draft", json={"revision": 0, "report": {"evidence": "Saved in tab one"}})
    assert first.status_code == 200
    conflict = client.put(base + "/draft", json={"revision": 0, "report": {"evidence": "Stale tab"}})
    assert conflict.status_code == 409
    assert client.get(base).json()["draft"]["report"]["evidence"] == "Saved in tab one"
    identity["id"] = 3
    assert client.get(base).status_code == 404
    assert client.put(base + "/draft", json={"revision": 1, "report": {}}).status_code == 404
    assert client.get("/api/v1/admin/competition-incidents").status_code == 403


def test_help_persists_and_runs_do_not_submit_or_award(published):
    client, session, identity, comp_id, part = published
    gameplay(client, part)
    base = f"/api/v1/competition-sessions/{part}/items/gameplay:0"
    assert client.post(base + "/help").json()["level"] == 1
    assert client.get(base).json()["checkpoints"] == ["Compare people with the directory."]
    run = client.post(base + "/runs", json={"query": "SELECT * FROM missing_table"})
    assert run.status_code == 200 and not run.json()["success"]
    summary = client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]
    assert summary["points"] == 0
    assert not next(i for i in summary["items"] if i["key"] == "gameplay:0")["submitted"]


def test_enabled_flag_and_staff_preparation(environment, monkeypatch):
    client, session, identity, engine = environment
    monkeypatch.setattr(settings, "COMPETITIONS_ENABLED", False)
    assert client.get("/api/v1/competitions/capabilities").json() == {"enabled": False}
    assert client.get("/api/v1/competitions").status_code == 404
    assert client.get("/api/v1/admin/competition-incidents").status_code == 200


def test_snapshot_and_export_reconciliation(published):
    client, session, identity, comp_id, part = published
    gameplay(client, part)
    result, _ = report(client, part, "gameplay:0", correct=True)
    identity["id"] = 1
    version = session.query(CompetitionIncidentVersion).first()
    before = json.dumps(version.document, sort_keys=True)
    row = client.get(f"/api/v1/admin/competition-incidents/{version.incident_id}").json()
    changed = copy.deepcopy(row["document"]); changed["complaint"] = "An updated complaint in the source draft only."
    response = client.put(f"/api/v1/admin/competition-incidents/{version.incident_id}", json={"document": changed, "revision": row["revision"]})
    assert response.status_code == 200
    session.expire_all()
    assert json.dumps(session.get(CompetitionIncidentVersion, version.id).document, sort_keys=True) == before
    export = client.get(f"/api/v1/admin/competitions/{comp_id}/exports/outcomes")
    assert export.status_code == 200 and "missing" in export.text
    assert "student@example.test" not in export.text
    review = client.post(f"/api/v1/admin/competition-submissions/{result['id']}/reviews", json={"diagnosis_score": 2, "explanation_score": 1, "rationale": "Reasonable hypothesis; limited consequence evidence."})
    assert review.status_code == 200
    assert client.get(f"/api/v1/admin/competitions/{comp_id}/submissions").json()[0]["reviews"][0]["diagnosis_score"] == 2


def test_typed_comparator_keeps_duplicates_aliases_precision_and_whitespace():
    same = lambda rows, cols=["a", "a"]: {"columns": cols, "rows": rows}
    assert matches(same([[1, 2], [1, 2]]), same([[1, 2], [1, 2]]))
    assert not matches(same([[1, 2]]), same([[1, 2], [1, 2]]))
    assert not matches(same([[1, 2]]), same([[9, 2]]))
    assert not matches(same([[9007199254740993, "a  b"]]), same([[9007199254740992, "a b"]]))
    assert not matches(same([[None, ""]]), same([["", None]]))
    assert matches(same([[2, 1], [1, 2]]), same([[1, 2], [2, 1]]))
    assert not matches(same([[2, 1], [1, 2]]), same([[1, 2], [2, 1]]), order_sensitive=True)
    assert not matches(same([], ["wrong"]), same([], ["expected"]))


@pytest.mark.parametrize("query", ["DROP TABLE Safe", "SELECT 1; SELECT 2", "ATTACH DATABASE ':memory:' AS other", "PRAGMA writable_schema=ON", "SELECT load_extension('bad')", "SELECT random()"])
def test_executor_rejects_writes_stacked_queries_and_unsafe_functions(environment, query):
    result = execute("CREATE TABLE Safe(id INTEGER);", "INSERT INTO Safe VALUES (1);", query)
    assert not result["success"]
    assert execute("CREATE TABLE Safe(id INTEGER);", "INSERT INTO Safe VALUES (1);", "SELECT id FROM Safe")["rows"] == [[1]]


def test_comments_strings_limits_and_cooperative_deadline(environment, monkeypatch):
    schema = "CREATE TABLE Safe(id INTEGER);"
    assert execute(schema, "", "-- a harmless comment\nSELECT 'UPDATE; is text' AS value")["success"]
    preview = execute(schema, "", "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<300) SELECT x FROM n", preview=True)
    assert preview["truncated"] and len(preview["rows"]) == 200
    monkeypatch.setattr(settings, "COMPETITION_QUERY_SECONDS", 0.02)
    result = execute(schema, "", "WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<100000000) SELECT SUM(x) FROM n")
    assert not result["success"] and result["execution_time_ms"] < 1500


def test_source_adapter_idempotence_and_quarantine(environment):
    client, session, identity, engine = environment
    raw = {"id": "175", "title": "Two Tables", "sql_schema": "CREATE TABLE Person(id int, name varchar(20)); CREATE TABLE Address(personId int, city varchar(20)); TRUNCATE TABLE Person; INSERT INTO Person VALUES (1,'A');", "answer": "SELECT p.name,a.city FROM Person p LEFT JOIN Address a ON p.id=a.personId"}
    first = client.post("/api/v1/admin/competition-sources/import", json={"entries": [raw], "authorised": True})
    assert first.status_code == 200 and first.json()[0]["eligible"]
    again = client.post("/api/v1/admin/competition-sources/import", json={"entries": [raw], "authorised": True})
    assert first.json()[0]["id"] == again.json()[0]["id"]
    bad = client.post("/api/v1/admin/competition-sources/import", json={"entries": [{"id": "bad", "title": "Missing answer"}]})
    assert bad.status_code == 200 and not bad.json()[0]["eligible"]
    snap, _ = normalise_source(raw)
    adapted = adaptation(snap, "left_to_inner", "A person disappeared from the directory.", "All people must be visible, with NULL for missing addresses.")
    assert not validate_document(adapted)["valid"]  # Duplicate placeholder fixtures and unconfirmed oracle.


def test_validation_rejects_wrong_oracle_runtime_fault_and_equivalent_mutant(environment):
    valid = document()
    assert validate_document(valid)["valid"]
    wrong = copy.deepcopy(valid); wrong["scenarios"][0]["approved_outputs"]["directory"]["rows"] = []
    assert not validate_document(wrong)["valid"]
    bad = copy.deepcopy(valid); bad["components"][0]["query"] = "SELECT missing FROM nowhere"
    assert not validate_document(bad)["valid"]
    equivalent = copy.deepcopy(valid); equivalent["components"][0]["query"] = equivalent["components"][0]["reference_query"]
    assert not validate_document(equivalent)["valid"]


def test_migration_is_idempotent_and_preserves_users(environment):
    client, session, identity, engine = environment
    from run_competition_migration import migrate
    assert migrate(engine) == migrate(engine)
    assert session.execute(select(func.count()).select_from(CompetitionParticipation)).scalar() == 0
    assert session.get(__import__('app.models.user', fromlist=['User']).User, 2).email == 'student@example.test'
    ddl = str(CreateTable(CompetitionSubmission.__table__).compile(dialect=postgresql.dialect()))
    assert 'UNIQUE (participation_id, request_key)' in ddl


def test_source_permission_and_review_confirmation_enable_approval(environment):
    client, session, identity, engine = environment
    doc = document("Approval")
    raw = {"id": "approval-source", "title": "Approval exercise", "schema_sql": doc["schema_sql"],
           "sample_data_sql": doc["scenarios"][0]["seed_sql"], "correct_answer_query": doc["components"][0]["reference_query"]}
    imported = client.post("/api/v1/admin/competition-sources/import", json={"entries": [raw]})
    assert imported.status_code == 200 and not imported.json()[0]["authorised"]
    source_id = imported.json()[0]["id"]
    doc["oracle_confirmed"] = False
    incident = client.post("/api/v1/admin/competition-incidents", json={"document": doc, "source_id": source_id}).json()
    incident_id = incident["id"]
    checked = client.post(f"/api/v1/admin/competition-incidents/{incident_id}/validate")
    assert not checked.json()["valid"] and "review checkbox" in checked.json()["errors"][0]
    doc["oracle_confirmed"] = True  # The UI review checkbox supplies this field.
    saved = client.put(f"/api/v1/admin/competition-incidents/{incident_id}", json={"document": doc, "source_id": source_id, "revision": incident["revision"]})
    assert saved.status_code == 200
    assert client.post(f"/api/v1/admin/competition-incidents/{incident_id}/validate").json()["valid"]
    assert client.post(f"/api/v1/admin/competition-incidents/{incident_id}/approve").status_code == 400
    permission = client.post(f"/api/v1/admin/competition-sources/{source_id}/authorise")
    assert permission.status_code == 200 and permission.json()["authorised"]
    assert client.get(f"/api/v1/admin/competition-sources/{source_id}").json()["authorised"]
    approved = client.post(f"/api/v1/admin/competition-incidents/{incident_id}/approve")
    assert approved.status_code == 200, approved.text
    version = approved.json()["version_id"]
    assert client.post(f"/api/v1/admin/competition-incidents/{incident_id}/approve").json()["version_id"] == version
    assert version in {row["id"] for row in client.get("/api/v1/admin/competition-incident-versions").json()}
    reopened = client.get(f"/api/v1/admin/competition-incidents/{incident_id}").json()
    assert reopened["document"]["oracle_confirmed"] and reopened["status"] == "approved"
    assert "/api/v1/admin/competitions/pilot" not in client.app.openapi()["paths"]


def test_bank_question_can_be_snapshotted_and_adapted_without_changing_original(environment):
    client, session, identity, engine = environment
    from app.models.question import Question, Difficulty
    doc = document("Bank")
    reference = doc["components"][0]["reference_query"]
    question = Question(title="Existing bank exercise", description=doc["business_rules"], difficulty=Difficulty.MEDIUM,
                        schema_sql=doc["schema_sql"], sample_data_sql=doc["scenarios"][0]["seed_sql"],
                        correct_answer_query=reference, correct_answer_hash="bank-test", db_file_path="unused-bank-test.db", created_by=1)
    session.add(question)
    session.commit()
    question_id = question.id
    imported = client.post(f"/api/v1/admin/competition-sources/from-question/{question_id}")
    assert imported.status_code == 200 and imported.json()["eligible"], imported.text
    source_id = imported.json()["id"]
    assert client.post(f"/api/v1/admin/competition-sources/from-question/{question_id}").json()["id"] == source_id
    assert client.post(f"/api/v1/admin/competition-sources/{source_id}/authorise").json()["authorised"]
    adapted = client.post(f"/api/v1/admin/competition-sources/{source_id}/adapt", json={
        "template": "left_to_inner", "complaint": doc["complaint"], "business_rules": doc["business_rules"]})
    assert adapted.status_code == 200, adapted.text
    result = client.get(f"/api/v1/admin/competition-incidents/{adapted.json()['id']}").json()
    assert result["source_id"] == source_id and not result["document"]["oracle_confirmed"]
    assert "INNER JOIN" in result["document"]["components"][0]["query"]
    session.expire_all()
    assert session.get(Question, question_id).correct_answer_query == reference


def test_execution_lease_blocks_competing_requests(published):
    client, session, identity, comp_id, part = published
    from app.services.competition import acquire, release
    gameplay(client, part)
    token = acquire(session, 2)
    try:
        response = client.post(f'/api/v1/competition-sessions/{part}/items/gameplay:0/runs', json={'query': 'SELECT 1'})
        assert response.status_code == 409
    finally:
        release(session, 2, token)
    assert client.post(f'/api/v1/competition-sessions/{part}/items/gameplay:0/runs', json={'query': 'SELECT 1'}).status_code == 200


def test_judge_failure_preserves_participation_and_retries_frozen_report(published, monkeypatch):
    client, session, identity, comp_id, part = published
    from app.services import competition as service
    original = service.judge
    def broken(*_args):
        raise OSError("Synthetic fixture-store outage")
    monkeypatch.setattr(service, "judge", broken)
    result, body = report(client, part, "gameplay:0", correct=True)
    assert result["status"] == "judge_error" and result["submitted"] and result["feedback"] is None
    assert client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]["items"][0]["submitted"]
    monkeypatch.setattr(service, "judge", original)
    identity["id"] = 1
    assert client.put(f"/api/v1/admin/competitions/{comp_id}/window", json={"closes_at": "2020-01-01T00:00:00Z"}).status_code == 200
    identity["id"] = 2
    recovered = client.post(f"/api/v1/competition-sessions/{part}/items/gameplay:0/submissions", json=body)
    assert recovered.status_code == 200 and recovered.json()["status"] == "graded"
    assert recovered.json()["id"] == result["id"] and recovered.json()["feedback"]["restored"]


def test_outcome_export_uses_latest_report_and_review_is_audited(published):
    client, session, identity, comp_id, part = published
    report(client, part, "gameplay:0", correct=True)
    latest, _ = report(client, part, "gameplay:0", correct=False)
    identity["id"] = 1
    import csv, io
    response = client.get(f"/api/v1/admin/competitions/{comp_id}/exports/outcomes")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert rows[0]["repair_correct"] == "False"
    assert len(rows) == 3 and rows[1]["submission_status"] == "missing"
    for mark in (1, 3):
        assert client.post(f"/api/v1/admin/competition-submissions/{latest['id']}/reviews", json={"diagnosis_score": mark, "explanation_score": mark, "rationale": "Reviewed against the cause and consequence rubric."}).status_code == 200
    reviews = client.get(f"/api/v1/admin/competitions/{comp_id}/submissions").json()[0]["reviews"]
    assert len(reviews) == 2 and reviews[0]["diagnosis_score"] == 3


def test_judge_outage_keeps_attempt_credit_and_staff_can_retry(published, monkeypatch):
    client, session, identity, comp_id, part = published
    from app.services import competition as service
    gameplay(client, part)
    original = service.judge
    def broken(*_args):
        raise OSError('Synthetic judging outage')
    monkeypatch.setattr(service, 'judge', broken)
    result, _ = report(client, part, 'gameplay:0', correct=True)
    assert result['status'] == 'judge_error'
    assert client.get(f'/api/v1/competitions/{comp_id}').json()['participation']['points'] == 0
    monkeypatch.setattr(service, 'judge', original)
    identity['id'] = 1
    retried = client.post(f"/api/v1/admin/competition-submissions/{result['id']}/retry")
    assert retried.status_code == 200 and retried.json()['feedback']['restored']
    identity['id'] = 2
    assert client.get(f'/api/v1/competitions/{comp_id}').json()['participation']['points'] == 10


def test_window_offsets_are_normalised_and_serialised_as_utc(published):
    client, session, identity, comp_id, part = published
    identity['id'] = 1
    response = client.put(f'/api/v1/admin/competitions/{comp_id}/window', json={
        'opens_at': '2030-01-02T18:00:00+08:00', 'closes_at': '2030-01-02T19:00:00+08:00'})
    assert response.status_code == 200
    assert response.json()['opens_at'].startswith('2030-01-02T10:00:00')
    assert response.json()['opens_at'].endswith(('Z', '+00:00'))
    identity['id'] = 2
    metadata = client.get(f'/api/v1/competitions/{comp_id}').json()
    assert metadata['closes_at'].startswith('2030-01-02T11:00:00')
    assert not metadata['open']
