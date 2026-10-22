"""RA questions over HTTP: staff authoring, what students may see, grading and attempts."""
import json

import pytest

from app.database import SessionLocal
from app.models.ra_question_part import RAQuestionPart
from app.services.ra.examples import TUTORIAL_Q1

Q1_II = "R1 := γ MIN(GPA)→MinGPA (STUDENT)\nR2 := STUDENT ⋈ STUDENT.GPA=R1.MinGPA R1\nAnswer := π Sname (R2)"
BASE = "/api/v1/ra/questions"


def payload(part_id=None, **changes):
    """A one-part question. ``model_answer``/``checkpoints`` go into the part (and stay at
    the top level too, which is the shape /validate takes)."""
    body = {"title": "Lowest GPA", "description": "Find the name(s) of student(s) with the lowest GPA.",
            "difficulty": "medium", "schema_sql": TUTORIAL_Q1["schema_sql"], "data_sql": "",
            "model_answer": Q1_II, "is_published": True}
    body.update(changes)
    body["parts"] = [{"id": part_id, "model_answer": body["model_answer"], "checkpoints": body.get("checkpoints")}]
    return body


@pytest.fixture
def created(client, staff_headers, ra_on):
    r = client.post(BASE, json=payload(), headers=staff_headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_everything_404s_while_off(client, staff_headers):
    assert client.get(BASE, headers=staff_headers).status_code == 404
    assert client.post(BASE, json=payload(), headers=staff_headers).status_code == 404


def test_students_cannot_author(client, student_headers, ra_on):
    assert client.post(BASE, json=payload(), headers=student_headers).status_code == 403
    assert client.post(f"{BASE}/validate", json=payload(), headers=student_headers).status_code == 403


def test_create_builds_and_stores_the_test_databases(created):
    [part] = created["parts"]
    assert part["suite"]["mutants"] > 0 and part["suite"]["mutants_killed"] == part["suite"]["mutants"]
    assert part["model_answer"] == Q1_II and part["label"] == "" and created["has_data"] is False
    assert [r["name"] for r in created["relations"]][:2] == ["STUDENT", "DEPT"]


@pytest.mark.parametrize("change, source", [
    ({"schema_sql": "CREATE TABL STUDENT (x INT);"}, "schema"),
    ({"data_sql": "INSERT INTO NOPE VALUES (1);"}, "data"),
    ({"model_answer": "π Nope STUDENT"}, "model_answer"),
    ({"checkpoints": [{"statement": "R9", "label": "x"}]}, "checkpoints"),
])
def test_invalid_input_names_the_field(client, staff_headers, ra_on, change, source):
    r = client.post(BASE, json=payload(**change), headers=staff_headers)
    assert r.status_code == 422 and r.json()["detail"]["source"] == source
    assert r.json()["detail"]["part"] == (0 if source in ("model_answer", "checkpoints") else None)
    v = client.post(f"{BASE}/validate", json=payload(**change), headers=staff_headers).json()
    assert v["ok"] is False and v["error_source"] == source


def test_validate_previews_without_saving(client, staff_headers, ra_on):
    before = client.get(BASE, headers=staff_headers).json()
    v = client.post(f"{BASE}/validate", json=payload(), headers=staff_headers).json()
    assert v["ok"] and v["suite"]["databases"] > 0 and v["model_result_source"] == "generated"
    assert [c["statement"] for c in v["checkpoints"]] == ["R1", "R2", None]
    assert client.get(BASE, headers=staff_headers).json() == before


def test_students_never_see_the_model_answer(client, student_headers, created):
    r = client.get(f"{BASE}/{created['id']}", headers=student_headers)
    assert r.status_code == 200
    body = json.dumps(r.json())
    assert "model_answer" not in body and "MinGPA" not in body and "suite" not in body
    assert r.json()["parts"][0]["id"] == created["parts"][0]["id"]
    assert client.get(f"{BASE}/{created['id']}/edit", headers=student_headers).status_code == 403


def test_drafts_are_hidden_from_students(client, staff_headers, student_headers, ra_on):
    draft = client.post(BASE, json=payload(is_published=False), headers=staff_headers).json()
    assert client.get(f"{BASE}/{draft['id']}", headers=student_headers).status_code == 404
    assert draft["id"] not in [q["id"] for q in client.get(BASE, headers=student_headers).json()]
    assert draft["id"] in [q["id"] for q in client.get(BASE, headers=staff_headers).json()]


def test_submit_grades_records_and_tracks_progress(client, student_headers, created):
    qid = created["id"]
    wrong = client.post(f"{BASE}/{qid}/submit", json={"answer": Q1_II.replace("MIN", "MAX")},
                        headers=student_headers).json()
    assert wrong["grade"]["verdict"] == "wrong_in_general" and wrong["grade"]["counterexample"]
    assert [s["status"] for s in wrong["grade"]["steps"]] == ["close", "close", "close"]
    assert wrong["structure_source"] == "generated" and len(wrong["structure"]["steps"]) == 3
    right = client.post(f"{BASE}/{qid}/submit", json={"answer": Q1_II}, headers=student_headers).json()
    assert right["grade"]["verdict"] == "correct"
    history = client.get(f"{BASE}/{qid}/attempts", headers=student_headers).json()
    assert [a["verdict"] for a in history][:2] == ["correct", "wrong_in_general"]
    item = next(q for q in client.get(BASE, headers=student_headers).json() if q["id"] == qid)
    assert item["solved"] is True and item["attempts"] >= 2


def test_check_runs_without_recording(client, student_headers, created):
    qid = created["id"]
    before = len(client.get(f"{BASE}/{qid}/attempts", headers=student_headers).json())
    r = client.post(f"{BASE}/{qid}/check", json={"answer": "π Sname STUDENT"}, headers=student_headers).json()
    assert r["ok"] and r["source"] == "generated" and r["result"]["columns"] == ["Sname"]
    bad = client.post(f"{BASE}/{qid}/check", json={"answer": "π Nope STUDENT"}, headers=student_headers).json()
    assert not bad["ok"] and bad["error"]["code"] == "RA003"
    assert len(client.get(f"{BASE}/{qid}/attempts", headers=student_headers).json()) == before


def test_hide_correctness_only_says_submitted(client, staff_headers, student_headers, ra_on):
    q = client.post(BASE, json=payload(hide_correctness=True), headers=staff_headers).json()
    r = client.post(f"{BASE}/{q['id']}/submit", json={"answer": Q1_II}, headers=student_headers).json()
    assert r["grade"] is None and r["attempt_id"]
    assert client.get(f"{BASE}/{q['id']}/attempts", headers=student_headers).json()[0]["verdict"] is None


def test_step_direction_can_be_switched_off(client, staff_headers, student_headers, ra_on):
    q = client.post(BASE, json=payload(show_step_direction=False), headers=staff_headers).json()
    r = client.post(f"{BASE}/{q['id']}/submit", json={"answer": Q1_II.replace("MIN", "MAX")},
                    headers=student_headers).json()
    assert r["grade"]["verdict"] == "wrong_in_general"
    assert all(s["status"] == "none" and s["checkpoint"] is None for s in r["grade"]["steps"])


def test_editing_the_title_keeps_the_test_databases_but_new_content_rebuilds_them(client, staff_headers, created):
    qid = created["id"]

    pid = created["parts"][0]["id"]

    def stored_suite():
        db = SessionLocal()
        try:
            return db.query(RAQuestionPart).get(pid).suite_json
        finally:
            db.close()
    before = stored_suite()
    client.put(f"{BASE}/{qid}", json=payload(pid, title="Lowest GPA (renamed)"), headers=staff_headers)
    assert stored_suite() == before
    r = client.put(f"{BASE}/{qid}", json=payload(pid, model_answer="π Sname (STUDENT ⋈ GPA = m γ MIN(GPA) → m STUDENT)"),
                   headers=staff_headers)
    assert r.status_code == 200 and stored_suite() != before
    assert [p["id"] for p in r.json()["parts"]] == [pid]          # the same part, so its attempts stay


def test_delete_hides_it(client, staff_headers, student_headers, created):
    assert client.delete(f"{BASE}/{created['id']}", headers=staff_headers).status_code == 204
    assert client.get(f"{BASE}/{created['id']}", headers=student_headers).status_code == 404


# ── questions with parts ─────────────────────────────────────────────────────
Q1_I = "R1 := σ Numphds < 50 (DEPT)\nAnswer := π Pname (PROF ⋈ R1)"


def two_parts(**changes):
    body = payload(**changes)
    body["parts"] = [{"label": "(i)", "description": "Professors in small departments.", "marks": 1,
                      "model_answer": Q1_I},
                     {"label": "(ii)", "description": "Students with the lowest GPA.", "marks": 3,
                      "model_answer": Q1_II}]
    return body


def test_parts_are_answered_one_at_a_time(client, staff_headers, student_headers, ra_on):
    q = client.post(BASE, json=two_parts(), headers=staff_headers).json()
    p1, p2 = q["parts"]
    assert (p1["label"], p1["marks"], p2["label"], p2["marks"]) == ("(i)", 1, "(ii)", 3)
    assert p1["suite"]["databases"] > 0 and p2["suite"]["databases"] > 0
    url = f"{BASE}/{q['id']}"

    # With several parts an answer must say which part it is for.
    assert client.post(f"{url}/submit", json={"answer": Q1_II}, headers=student_headers).status_code == 422
    # Part (ii)'s answer is wrong for part (i), and right for part (ii).
    wrong = client.post(f"{url}/submit", json={"answer": Q1_II, "part_id": p1["id"]}, headers=student_headers).json()
    assert wrong["part_id"] == p1["id"] and wrong["grade"]["verdict"] == "wrong_columns"
    right = client.post(f"{url}/submit", json={"answer": Q1_II, "part_id": p2["id"]}, headers=student_headers).json()
    assert right["grade"]["verdict"] == "correct"

    seen = client.get(url, headers=student_headers).json()
    assert [(p["solved"], p["attempts"]) for p in seen["parts"]] == [(False, 1), (True, 1)]
    assert seen["solved"] is False and "model_answer" not in json.dumps(seen)
    item = next(x for x in client.get(BASE, headers=student_headers).json() if x["id"] == q["id"])
    assert (item["parts_total"], item["parts_solved"], item["solved"]) == (2, 1, False)
    history = client.get(f"{url}/attempts", headers=student_headers).json()
    assert {a["part_id"] for a in history} == {p1["id"], p2["id"]}

    client.post(f"{url}/submit", json={"answer": Q1_I, "part_id": p1["id"]}, headers=student_headers)
    assert client.get(url, headers=student_headers).json()["solved"] is True


def test_a_wrong_part_names_its_index_and_saves_nothing(client, staff_headers, ra_on):
    before = client.get(BASE, headers=staff_headers).json()
    body = two_parts()
    body["parts"][1]["model_answer"] = "π Nope STUDENT"
    r = client.post(BASE, json=body, headers=staff_headers)
    assert r.status_code == 422 and r.json()["detail"]["source"] == "model_answer" and r.json()["detail"]["part"] == 1
    assert client.get(BASE, headers=staff_headers).json() == before


def test_removing_a_part_keeps_the_others(client, staff_headers, student_headers, ra_on):
    q = client.post(BASE, json=two_parts(), headers=staff_headers).json()
    p1, p2 = q["parts"]
    body = two_parts()
    body["parts"] = [dict(body["parts"][1], id=p2["id"])]
    r = client.put(f"{BASE}/{q['id']}", json=body, headers=staff_headers).json()
    assert [p["id"] for p in r["parts"]] == [p2["id"]]
    # Now a single part, so answers need not name it.
    ok = client.post(f"{BASE}/{q['id']}/submit", json={"answer": Q1_II}, headers=student_headers).json()
    assert ok["part_id"] == p2["id"] and ok["grade"]["verdict"] == "correct"
