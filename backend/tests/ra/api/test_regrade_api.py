"""Proved or tested, over HTTP: what staff and students see, the analytics counts, and the
staff regrade of past attempts (services/ra/regrade.py)."""
from app.database import SessionLocal
from app.models.ra_attempt import RAAttempt

BASE = "/api/v1/ra/questions"
ANALYTICS = "/api/v1/ra/analytics/questions"
UNI = """
CREATE TABLE Course (cid INTEGER PRIMARY KEY, title TEXT NOT NULL);
CREATE TABLE Student (sid INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE Enrolled (sid INTEGER NOT NULL REFERENCES Student(sid), cid INTEGER NOT NULL REFERENCES Course(cid),
                       PRIMARY KEY (sid, cid));
"""
REDUNDANT_JOIN = "Π sid (Enrolled ⋈ Course)"        # right: every enrolment has its course


def _question(client, staff_headers):
    r = client.post(BASE, headers=staff_headers, json={
        "title": "Who is enrolled", "description": "Ids of enrolled students.", "schema_sql": UNI,
        "is_published": True, "answer_format": "mixed", "parts": [{"model_answer": "Π sid (Enrolled)"}]})
    assert r.status_code == 201, r.text
    return r.json()


def _submit(client, headers, q, answer):
    r = client.post(f"{BASE}/{q['id']}/submit", headers=headers, json={"part_id": q["parts"][0]["id"], "answer": answer})
    assert r.status_code == 200, r.text
    return r.json()


def _as_old_grader(attempt_id: int, **fields):
    """Make a stored attempt look as an earlier grader left it."""
    db = SessionLocal()
    try:
        a = db.query(RAAttempt).get(attempt_id)
        for k, v in fields.items():
            setattr(a, k, v)
        db.commit()
    finally:
        db.close()


def test_staff_see_how_a_verdict_was_reached_and_students_do_not(client, staff_headers, student_headers, ra_on):
    q = _question(client, staff_headers)
    mine = _submit(client, student_headers, q, REDUNDANT_JOIN)["grade"]
    assert mine["verdict"] == "correct" and mine["method"] is None and mine["proof"] is None
    staff = _submit(client, staff_headers, q, REDUNDANT_JOIN)["grade"]
    assert staff["method"] == "proof" and staff["proof"] == "whole"
    assert mine["message"] == staff["message"]


def test_analytics_count_proved_and_tested_correct_answers(client, staff_headers, student_headers, ra_on):
    q = _question(client, staff_headers)
    _submit(client, student_headers, q, REDUNDANT_JOIN)
    _submit(client, student_headers, q, "Π sid (Student)")                       # wrong
    data = client.get(f"{ANALYTICS}/{q['id']}", headers=staff_headers).json()
    assert data["parts"][0]["correct_by"] == {"proved": 1, "tested": 0}
    sid = data["students"][0]["user_id"]
    attempts = client.get(f"{ANALYTICS}/{q['id']}/students/{sid}", headers=staff_headers).json()["attempts"]
    assert [a["method"] for a in attempts] == ["proof", "tested"]
    assert attempts[1]["databases_checked"] > 0


def test_regrading_shows_the_changes_first_and_keeps_overrides(client, staff_headers, student_headers, ra_on):
    q = _question(client, staff_headers)
    right = _submit(client, student_headers, q, REDUNDANT_JOIN)["attempt_id"]
    overridden = _submit(client, student_headers, q, REDUNDANT_JOIN)["attempt_id"]
    untouched = _submit(client, student_headers, q, "Π sid (Student)")["attempt_id"]
    # The old grader ignored foreign keys and marked the redundant join wrong.
    for aid in (right, overridden):
        _as_old_grader(aid, verdict="wrong_in_general", is_correct=0, method="proof")
    _as_old_grader(overridden, override_is_correct=0)

    preview = client.post(f"{ANALYTICS}/{q['id']}/regrade/preview", headers=staff_headers, json={}).json()
    assert preview["done"] and preview["total"] == 3 and preview["checked"] == 3
    changes = {c["attempt_id"]: c for c in preview["changes"]}
    assert set(changes) == {right, overridden}
    assert changes[right]["old"]["verdict"] == "wrong_in_general" and changes[right]["new"]["verdict"] == "correct"
    assert changes[right]["verdict_changed"] and changes[overridden]["overridden"]
    # Nothing has changed yet.
    data = client.get(f"{ANALYTICS}/{q['id']}", headers=staff_headers).json()
    assert data["parts"][0]["verdicts"]["correct"] == 0

    applied = client.post(f"{ANALYTICS}/{q['id']}/regrade/apply", headers=staff_headers,
                          json={"attempt_ids": [right, overridden, untouched]}).json()
    assert applied == {"changed": 2}
    db = SessionLocal()
    try:
        a, o = db.query(RAAttempt).get(right), db.query(RAAttempt).get(overridden)
        assert (a.verdict, a.is_correct, a.method) == ("correct", 1, "proof")
        assert o.verdict == "correct" and o.override_is_correct == 0          # the staff mark still decides
    finally:
        db.close()
    again = client.post(f"{ANALYTICS}/{q['id']}/regrade/preview", headers=staff_headers, json={}).json()
    assert again["changes"] == []


def test_regrading_goes_in_batches(client, staff_headers, student_headers, ra_on, monkeypatch):
    from app.services.ra import regrade
    monkeypatch.setattr(regrade, "BATCH_SECONDS", 0.0)                 # one attempt per batch
    q = _question(client, staff_headers)
    for answer in (REDUNDANT_JOIN, "Π sid (Student)"):
        _submit(client, student_headers, q, answer)
    first = client.post(f"{ANALYTICS}/{q['id']}/regrade/preview", headers=staff_headers, json={}).json()
    assert first["checked"] == 1 and not first["done"]
    second = client.post(f"{ANALYTICS}/{q['id']}/regrade/preview", headers=staff_headers,
                         json={"after_id": first["after_id"]}).json()
    assert second["checked"] == 2 and second["done"]


def test_students_cannot_regrade(client, staff_headers, student_headers, ra_on):
    q = _question(client, staff_headers)
    assert client.post(f"{ANALYTICS}/{q['id']}/regrade/preview", headers=student_headers, json={}).status_code == 403
    assert client.post(f"{ANALYTICS}/{q['id']}/regrade/apply", headers=student_headers,
                       json={"attempt_ids": []}).status_code == 403


def test_the_suite_report_says_which_surviving_variants_are_equivalent(client, staff_headers, ra_on):
    q = client.post(f"{BASE}/validate", headers=staff_headers, json={
        "schema_sql": UNI, "model_answer": "Π sid (Enrolled ⋈ Course)"}).json()
    assert q["ok"]
    # Joining Course changes nothing (foreign key), so "⋈ removed" can't be caught: proved equivalent.
    survivors = q["suite"]["surviving_mutants"]
    assert survivors and all(m["equivalent"] is True for m in survivors)
