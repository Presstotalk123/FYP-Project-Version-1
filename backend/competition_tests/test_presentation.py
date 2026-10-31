"""Presentation examples, mission-only progression and competition scoring."""
import copy
from datetime import timedelta
import json
from pathlib import Path
import uuid

import pytest

from app.models.competition import Competition, CompetitionParticipation, CompetitionSubmission
from app.services.competition import now
from app.services.incident_authoring import validate_document
from test_competition import report


@pytest.fixture
def slides(environment):
    client, session, identity, _engine = environment
    definitions = json.loads((Path(__file__).resolve().parents[1] / "app/data/database_rescue_slides.json").read_text(encoding="utf-8"))
    docs, versions = [], []
    for entry in definitions:
        doc = copy.deepcopy(entry["document"])
        doc["oracle_confirmed"] = True
        created = client.post("/api/v1/admin/competition-incidents", json={"document": doc})
        assert created.status_code == 200, created.text
        incident_id = created.json()["id"]
        validation = client.post(f"/api/v1/admin/competition-incidents/{incident_id}/validate")
        assert validation.json()["valid"], validation.text
        approved = client.post(f"/api/v1/admin/competition-incidents/{incident_id}/approve")
        versions.append(approved.json()["version_id"])
        docs.append(doc)
    created = client.post("/api/v1/admin/competitions", json={"title": "Presentation Joins", "topic": "joins", "description": "Easy and Medium examples.", "config": {"missions": versions}})
    assert created.status_code == 200, created.text
    comp_id = created.json()["id"]
    published = client.post(f"/api/v1/admin/competitions/{comp_id}/publish")
    assert published.status_code == 200, published.text
    assert published.json()["config"]["points"] == {"easy": 10, "medium": 20, "hard": 30}
    identity["id"] = 2
    part = client.post(f"/api/v1/competitions/{comp_id}/join").json()["participation_id"]
    return client, session, identity, comp_id, part, docs


def answer(client, part, index, sql, *, verdict="incorrect", explanation="The join does not meet the required output. This repair preserves the required records."):
    base = f"/api/v1/competition-sessions/{part}/items/gameplay:{index}"
    data = client.get(base).json()
    saved = client.put(base + "/draft", json={"revision": data["draft"]["revision"], "report": {
        "component_id": data["components"][0]["id"], "verdict": verdict, "repair_sql": sql, "explanation": explanation}})
    assert saved.status_code == 200, saved.text
    return client.post(base + "/submissions", json={"revision": saved.json()["revision"], "request_key": uuid.uuid4().hex})


def test_visible_examples_match_slides_and_keep_answer_keys_private(slides):
    client, session, identity, comp_id, part, docs = slides
    detail = client.get(f"/api/v1/competitions/{comp_id}").json()
    assert [(i["title"], i["points"]) for i in detail["participation"]["items"]] == [("Empty student directory", 10), ("Missing residents", 20)]
    easy = client.get(f"/api/v1/competition-sessions/{part}/items/gameplay:0").json()
    assert easy["features"][0]["output"]["rows"] == []
    students = next(t for t in easy["database"] if t["name"] == "Students")
    assert students["rows"] == [[1, "Alice", 20], [2, "Ben", 10]]
    assert "s.student_id = d.department_id" in easy["components"][0]["query"]
    medium = client.get(f"/api/v1/competition-sessions/{part}/items/gameplay:1").json()
    assert medium["features"][0]["output"]["rows"] == [[1, "Ava", 1]]
    assert "WHERE t.status = 'OPEN'" in medium["components"][0]["query"]
    assert all(field not in json.dumps(medium) for field in ("reference_query", "approved_outputs", "fault_cause", "overlapping_ids", "multiple_tickets"))


def test_slide_answers_require_verdict_and_explanation_but_no_extra_report_fields(slides):
    client, session, identity, comp_id, part, docs = slides
    correct = docs[0]["components"][0]["reference_query"]
    assert answer(client, part, 0, correct, verdict="").status_code == 400
    assert answer(client, part, 0, correct, explanation=" ").status_code == 400
    assert answer(client, part, 0, " ").status_code == 400
    # A 'correct' verdict judges the original query, not a hidden edited repair.
    wrong_verdict = answer(client, part, 0, correct, verdict="correct")
    assert wrong_verdict.status_code == 200 and not wrong_verdict.json()["feedback"]["restored"]
    assert not wrong_verdict.json()["feedback"]["verdict_correct"]
    stored = session.get(CompetitionSubmission, wrong_verdict.json()["id"])
    assert stored.payload["repair_sql"] == docs[0]["components"][0]["query"]
    correct_result = answer(client, part, 0, correct)
    assert correct_result.status_code == 200 and correct_result.json()["feedback"]["restored"]
    assert answer(client, part, 0, correct).json()["feedback"]["restored"]
    data = client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]
    assert data["points"] == 10 and not data["participation_complete"]
    # Incorrect final answers satisfy participation but earn no answer points.
    incorrect = answer(client, part, 1, docs[1]["components"][0]["query"])
    assert incorrect.status_code == 200 and not incorrect.json()["feedback"]["restored"]
    data = client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]
    assert data["points"] == 10 and data["participation_complete"] and data["phase"] == "complete"


def test_equivalent_repairs_pass_and_checks_do_not_award_points(slides):
    client, session, identity, comp_id, part, docs = slides
    easy = "SELECT s.student_name, d.department_name FROM Departments d, Students s WHERE s.department_id=d.department_id ORDER BY s.student_id"
    base = f"/api/v1/competition-sessions/{part}/items/gameplay:0"
    checked = client.post(base + "/checks", json={"query": easy, "component_id": "directory"})
    assert checked.json()["restored"]
    assert client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]["points"] == 0
    assert answer(client, part, 0, easy).json()["feedback"]["restored"]
    medium = "SELECT r.resident_id, r.resident_name, (SELECT COUNT(*) FROM Tickets t WHERE t.resident_id=r.resident_id AND t.status='OPEN') AS open_tickets FROM Residents r ORDER BY r.resident_id"
    assert answer(client, part, 1, medium).json()["feedback"]["restored"]
    data = client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]
    assert data["points"] == 30 and data["participation_complete"] and data["badges"] == ["Joins Rescuer"]


def test_hidden_fixtures_reject_sample_only_and_zero_count_shortcuts(slides):
    client, session, identity, comp_id, part, docs = slides
    hardcoded = "SELECT 'Alice' AS student_name, 'Business' AS department_name UNION ALL SELECT 'Ben', 'Engineering'"
    assert not answer(client, part, 0, hardcoded).json()["feedback"]["restored"]
    medium = docs[1]["components"][0]["reference_query"]
    assert not answer(client, part, 1, medium.replace("COUNT(t.ticket_id)", "COUNT(*)")).json()["feedback"]["restored"]
    false_fix = docs[1]["components"][0]["query"].replace("WHERE t.status = 'OPEN'", "WHERE t.status = 'OPEN' OR t.ticket_id IS NULL")
    assert not answer(client, part, 1, false_fix).json()["feedback"]["restored"]
    assert client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]["points"] == 0


def test_old_test_states_do_not_lock_missions_or_assistance(published):
    client, session, identity, comp_id, part_id = published
    part = session.get(CompetitionParticipation, part_id)
    part.phase, part.phase_active, part.form_order = "pre_test", 1, "AB"
    comp = session.get(Competition, comp_id)
    comp.config = {"missions": comp.config["missions"], "form_a": [987], "form_b": [988], "completion_xp": 10, "restoration_xp": {"easy": 40, "medium": 70, "hard": 100}}
    session.commit()
    detail = client.get(f"/api/v1/competitions/{comp_id}").json()["participation"]
    assert detail["phase"] == "gameplay" and len(detail["items"]) == 3
    assert client.get(f"/api/v1/competition-sessions/{part_id}/items/gameplay:0").status_code == 200
    assert client.post(f"/api/v1/competition-sessions/{part_id}/items/gameplay:0/help").status_code == 200
    assert client.get("/assistance").status_code == 200
    identity["id"] = 1
    current = client.get(f"/api/v1/admin/competitions/{comp_id}").json()["config"]
    assert "form_a" not in current and "form_b" not in current
    assert current["points"]["easy"] == 40  # Frozen legacy scoring is preserved.


def test_leaderboard_uses_points_then_successful_submission_time(published):
    client, session, identity, comp_id, first = published
    first_result, _ = report(client, first, "gameplay:0", correct=True)
    identity["id"] = 3
    second = client.post(f"/api/v1/competitions/{comp_id}/join").json()["participation_id"]
    second_result, _ = report(client, second, "gameplay:0", correct=True)
    instant = now() - timedelta(minutes=5)
    for part_id in (first, second):
        session.get(CompetitionParticipation, part_id).created_at = instant
    session.get(CompetitionSubmission, first_result["id"]).created_at = instant + timedelta(seconds=60)
    session.get(CompetitionSubmission, second_result["id"]).created_at = instant + timedelta(seconds=30)
    session.commit()
    board = client.get(f"/api/v1/competitions/{comp_id}").json()["leaderboard"]["rows"]
    assert [(r["rank"], r["points"], r["elapsed_seconds"]) for r in board] == [(1, 10, 30), (2, 10, 60)]
    assert board[0]["is_you"]
    # A later repeat does not change the once-awarded points or tie time.
    report(client, second, "gameplay:0", correct=True)
    board = client.get(f"/api/v1/competitions/{comp_id}").json()["leaderboard"]["rows"]
    assert board[0]["points"] == 10 and board[0]["elapsed_seconds"] == 30


def test_presentation_outputs_are_reviewed_not_generated_from_faulty_sql(environment):
    docs = json.loads((Path(__file__).resolve().parents[1] / "app/data/database_rescue_slides.json").read_text(encoding="utf-8"))
    for entry in docs:
        doc = entry["document"]
        assert not validate_document(doc)["valid"]  # Normal authoring still requires confirmation.
        doc["oracle_confirmed"] = True
        assert validate_document(doc)["valid"]
