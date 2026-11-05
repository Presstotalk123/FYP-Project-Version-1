"""The question type over HTTP: Mixed, Final answer and Multi-step questions, the staff
form's type switch and preview, and multi-step marks in assessments and analytics."""
import json

import pytest

from app.services.ra.tutorial_5_5 import UNIVERSITY

BASE = "/api/v1/ra/questions"
STEPS = [{"name": "R1", "prompt": "the Civil Engineering courses", "marks": 3,
          "model_answer": "π Dname, Cno (σ Dname = 'Civil Engineering' COURSE)"},
         {"name": "R2", "prompt": "who took which course", "marks": 3, "model_answer": "π Sid, Dname, Cno ENROLL"},
         {"name": "R3", "prompt": "students who took all of them", "marks": 2, "model_answer": "R2 ÷ R1"},
         {"name": None, "prompt": "their ids, names and GPAs", "marks": 2,
          "model_answer": "π Sid, Sname, GPA (R3 ⋈ STUDENT)"}]
MODEL = [s["model_answer"] for s in STEPS]
WRONG_R1 = ["π Dname, Cno (σ Dname = 'Computer Science' COURSE)"] + MODEL[1:]
IN_STEPS = "R1 := σ Numphds < 50 (DEPT)\nAnswer := π Pname (PROF ⋈ R1)"
ONE = "π Pname (PROF ⋈ σ Numphds < 50 DEPT)"


def question(answer_format, parts, **changes):
    body = {"title": f"{answer_format} question", "description": "Answer it.", "schema_sql": UNIVERSITY,
            "is_published": True, "answer_format": answer_format, "parts": parts}
    body.update(changes)
    return body


def multi_step(steps=None, **changes):
    return question("multi_step", [{"steps": steps if steps is not None else STEPS}], **changes)


@pytest.fixture
def steps_q(client, staff_headers, ra_on):
    r = client.post(BASE, json=multi_step(), headers=staff_headers)
    assert r.status_code == 201, r.text
    return r.json()


def submit(client, headers, q, **answer):
    return client.post(f"{BASE}/{q['id']}/submit", headers=headers, json={"part_id": q["parts"][0]["id"], **answer})


# ── Mixed and Final answer ───────────────────────────────────────────────────
def test_existing_questions_are_mixed(client, staff_headers, ra_on):
    q = client.post(BASE, json={"title": "t", "description": "d", "schema_sql": UNIVERSITY,
                                "parts": [{"model_answer": IN_STEPS}]}, headers=staff_headers).json()
    assert q["answer_format"] == "mixed" and q["parts"][0]["steps"] is None


def test_a_final_answer_model_answer_must_be_one_expression(client, staff_headers, ra_on):
    r = client.post(BASE, json=question("final_answer", [{"model_answer": IN_STEPS}]), headers=staff_headers)
    assert r.status_code == 422 and r.json()["detail"]["source"] == "model_answer" and r.json()["detail"]["part"] == 0
    assert "one expression" in r.json()["detail"]["message"]
    v = client.post(f"{BASE}/validate", headers=staff_headers,
                    json={"schema_sql": UNIVERSITY, "model_answer": IN_STEPS, "answer_format": "final_answer"}).json()
    assert v["ok"] is False and v["error_source"] == "model_answer"


def test_a_final_answer_question_refuses_steps_without_counting_them(client, staff_headers, student_headers, ra_on):
    q = client.post(BASE, json=question("final_answer", [{"model_answer": ONE}]), headers=staff_headers).json()
    assert client.get(f"{BASE}/{q['id']}", headers=student_headers).json()["answer_format"] == "final_answer"
    r = submit(client, student_headers, q, answer=IN_STEPS)
    assert r.status_code == 422 and "one expression" in r.json()["detail"]
    assert client.get(f"{BASE}/{q['id']}/attempts", headers=student_headers).json() == []
    graded = submit(client, student_headers, q, answer="π Pname (σ Numphds < 50 (DEPT) ⋈ PROF)").json()
    assert graded["grade"]["verdict"] == "correct"
    # No steps to compare with: Show structure gives no ✓/◐/○.
    assert {s["status"] for s in graded["grade"]["steps"]} == {"none"}


# ── Multi-step: authoring ────────────────────────────────────────────────────
def test_a_multi_step_part_is_built_from_its_steps(steps_q):
    [part] = steps_q["parts"]
    assert steps_q["answer_format"] == "multi_step" and part["marks"] == 10
    assert [s["name"] for s in part["steps"]] == ["R1", "R2", "R3", None]
    assert part["model_answer"].startswith("R1 := π Dname, Cno")
    assert [c["label"] for c in part["checkpoints"]][0] == "the Civil Engineering courses"


def test_students_see_the_prompts_but_never_the_step_answers(client, student_headers, steps_q):
    q = client.get(f"{BASE}/{steps_q['id']}", headers=student_headers).json()
    assert q["parts"][0]["steps"] == [{"name": s["name"], "prompt": s["prompt"], "marks": s["marks"]} for s in STEPS]
    assert "Civil Engineering'" not in json.dumps(q) and "÷" not in json.dumps(q)


@pytest.mark.parametrize("steps, step, words", [
    (STEPS[:1], None, "2 to 10 steps"),
    ([dict(STEPS[0], prompt=" ")] + STEPS[1:], 0, "needs a prompt"),
    ([dict(STEPS[0], name="COURSE")] + STEPS[1:], 0, "already a relation"),
    ([STEPS[0], dict(STEPS[1], name="R1")] + STEPS[2:], 1, "Two steps are called R1"),
    ([STEPS[0], dict(STEPS[1], model_answer="π Nope ENROLL")] + STEPS[2:], 1, "Nope"),
    ([STEPS[0], dict(STEPS[1], model_answer="")] + STEPS[2:], 1, "model answer"),
    ([dict(s, marks=0) for s in STEPS], None, "add up to 0"),
])
def test_step_errors_name_the_step(client, staff_headers, ra_on, steps, step, words):
    r = client.post(BASE, json=multi_step(steps), headers=staff_headers)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["source"] == "steps" and detail["part"] == 0 and detail["step"] == step and words in detail["message"]
    v = client.post(f"{BASE}/validate", headers=staff_headers,
                    json={"schema_sql": UNIVERSITY, "answer_format": "multi_step", "steps": steps}).json()
    assert v["ok"] is False and v["error_source"] == "steps" and v["error_step"] == step


# ── Multi-step: answering ────────────────────────────────────────────────────
def test_check_runs_every_box(client, student_headers, steps_q):
    r = client.post(f"{BASE}/{steps_q['id']}/check", headers=student_headers,
                    json={"part_id": steps_q["parts"][0]["id"], "step_answers": [MODEL[0], "", "R9", ""]}).json()
    assert r["ok"] and r["source"] == "example"
    assert [b["status"] for b in r["boxes"]] == ["ok", "empty", "error", "empty"]
    assert r["boxes"][0]["step"]["tree"]["columns"] == ["Dname", "Cno"]


def test_a_correct_answer_earns_every_mark(client, student_headers, steps_q):
    r = submit(client, student_headers, steps_q, step_answers=MODEL).json()
    assert r["grade"]["verdict"] == "correct"
    assert r["marking"]["earned"] == r["marking"]["total"] == 10
    assert {s["status"] for s in r["marking"]["steps"]} == {"full"}


def test_step_marks_with_carry_forward(client, student_headers, steps_q):
    r = submit(client, student_headers, steps_q, step_answers=WRONG_R1).json()
    marking = r["marking"]
    assert r["grade"]["verdict"] != "correct" and marking["earned"] == 7
    assert [(s["status"], s["earned"]) for s in marking["steps"]] == [
        ("missed", 0), ("reached", 3), ("carried", 2), ("carried", 2)]
    # The step that earned nothing shows the student's table and the model step's.
    first = marking["steps"][0]
    assert first["student"]["columns"] == first["expected"]["columns"] == ["Dname", "Cno"]
    assert first["structure"]["tree"]["op"] == "project"
    [attempt] = [a for a in client.get(f"{BASE}/{steps_q['id']}/attempts", headers=student_headers).json()
                 if a["step_answers"] == WRONG_R1]
    assert attempt["marks_earned"] == 7 and attempt["answer"].startswith("R1 := π Dname, Cno (σ Dname = 'Computer")


def test_an_empty_answer_is_not_submitted(client, student_headers, steps_q):
    assert submit(client, student_headers, steps_q, step_answers=["", " ", "", ""]).status_code == 422


def test_hidden_correctness_hides_the_marks(client, staff_headers, student_headers, ra_on):
    q = client.post(BASE, json=multi_step(hide_correctness=True), headers=staff_headers).json()
    r = submit(client, student_headers, q, step_answers=WRONG_R1).json()
    assert r["grade"] is None and r["marking"] is None
    [attempt] = client.get(f"{BASE}/{q['id']}/attempts", headers=student_headers).json()
    assert attempt["marks_earned"] is None and attempt["verdict"] is None


def test_hidden_direction_keeps_the_marks(client, staff_headers, student_headers, ra_on):
    q = client.post(BASE, json=multi_step(show_step_direction=False), headers=staff_headers).json()
    r = submit(client, student_headers, q, step_answers=WRONG_R1).json()
    assert r["marking"]["earned"] == 7
    assert {s["feedback"]["status"] for s in r["marking"]["steps"]} == {"none"}


# ── the type lock and the switch ─────────────────────────────────────────────
def test_the_type_is_locked_once_a_student_answered(client, staff_headers, student_headers, steps_q):
    submit(client, staff_headers, steps_q, step_answers=MODEL)            # staff trying it out: no lock
    edit = client.get(f"{BASE}/{steps_q['id']}/edit", headers=staff_headers).json()
    assert edit["has_attempts"] is False
    submit(client, student_headers, steps_q, step_answers=MODEL)
    assert client.get(f"{BASE}/{steps_q['id']}/edit", headers=staff_headers).json()["has_attempts"] is True
    body = question("mixed", [{"id": steps_q["parts"][0]["id"], "model_answer": steps_q["parts"][0]["model_answer"]}])
    r = client.put(f"{BASE}/{steps_q['id']}", json=body, headers=staff_headers)
    assert r.status_code == 422 and r.json()["detail"]["source"] == "answer_format"
    # Same type: editing still works.
    same = multi_step([dict(STEPS[0], prompt="the CE courses")] + STEPS[1:])
    same["parts"][0]["id"] = steps_q["parts"][0]["id"]
    assert client.put(f"{BASE}/{steps_q['id']}", json=same, headers=staff_headers).status_code == 200


def convert(client, headers, from_format, to_format, parts):
    r = client.post(f"{BASE}/convert-format", headers=headers, json={
        "schema_sql": UNIVERSITY, "from_format": from_format, "to_format": to_format, "parts": parts})
    assert r.status_code == 200 and r.json()["ok"], r.text
    return r.json()["parts"]


def test_switching_mixed_to_final_answer_joins_the_steps(client, staff_headers, ra_on):
    [part] = convert(client, staff_headers, "mixed", "final_answer", [{"model_answer": IN_STEPS, "marks": 2}])
    assert ":=" not in part["model_answer"] and part["model_answer"].startswith("Π Pname")
    assert part["checkpoints"] is None and part["error"] is None


def test_switching_mixed_to_multi_step_splits_the_statements(client, staff_headers, ra_on):
    [part] = convert(client, staff_headers, "mixed", "multi_step", [
        {"model_answer": IN_STEPS, "marks": 4, "checkpoints": [{"statement": "R1", "label": "small departments"}]}])
    assert [(s["name"], s["prompt"], s["marks"]) for s in part["steps"]] == [("R1", "small departments", 2),
                                                                            (None, "", 2)]
    [one] = convert(client, staff_headers, "final_answer", "multi_step", [{"model_answer": ONE, "marks": 3}])
    assert len(one["steps"]) == 1 and one["steps"][0]["marks"] == 3            # not split automatically


def test_switching_multi_step_back(client, staff_headers, ra_on):
    [mixed] = convert(client, staff_headers, "multi_step", "mixed", [{"steps": STEPS}])
    assert mixed["model_answer"].count(":=") == 3 and mixed["marks"] == 10
    assert mixed["checkpoints"][1]["label"] == "who took which course"
    [final] = convert(client, staff_headers, "multi_step", "final_answer", [{"steps": STEPS}])
    assert ":=" not in final["model_answer"] and "÷" in final["model_answer"]


def test_an_unreadable_part_is_left_for_staff(client, staff_headers, ra_on):
    [part] = convert(client, staff_headers, "mixed", "final_answer", [{"model_answer": "R1 := σ (", "marks": 1}])
    assert part["model_answer"] == "R1 := σ (" and "rewrite it by hand" in part["error"]


def test_the_preview_marks_like_a_submit(client, staff_headers, ra_on):
    r = client.post(f"{BASE}/try-steps", headers=staff_headers, json={
        "schema_sql": UNIVERSITY, "steps": STEPS, "step_answers": WRONG_R1}).json()
    assert r["ok"] and r["marking"]["earned"] == 7 and r["marking"]["source"] == "generated"
    bad = client.post(f"{BASE}/try-steps", headers=staff_headers, json={
        "schema_sql": UNIVERSITY, "steps": STEPS[:1], "step_answers": [""]}).json()
    assert bad["ok"] is False and bad["error_source"] == "steps"


def test_students_cannot_use_the_staff_tools(client, student_headers, ra_on):
    assert client.post(f"{BASE}/convert-format", headers=student_headers, json={
        "schema_sql": UNIVERSITY, "from_format": "mixed", "to_format": "final_answer", "parts": []}).status_code == 403
    assert client.post(f"{BASE}/try-steps", headers=student_headers, json={
        "schema_sql": UNIVERSITY, "steps": STEPS, "step_answers": MODEL}).status_code == 403


# ── marks in assessments and analytics ───────────────────────────────────────
def test_an_assessment_counts_the_step_marks(client, staff_headers, student_headers, ra_on):
    q = client.post(BASE, json=multi_step(), headers=staff_headers).json()
    a = client.post("/api/v1/assessments", headers=staff_headers, json={
        "title": "RA steps quiz", "items": [{"item_type": "ra_question", "item_id": q["id"], "weight": 100,
                                            "max_queries": 3}]}).json()
    client.post(f"/api/v1/assessments/{a['id']}/publish", headers=staff_headers)
    client.post(f"/api/v1/assessments/{a['id']}/start", headers=staff_headers)
    clone_id = client.get(f"/api/v1/assessments/{a['id']}", headers=staff_headers).json()["items"][0]["item_id"]
    client.post(f"/api/v1/student-assessments/{a['id']}/join", headers=student_headers, json={})
    clone = client.get(f"{BASE}/{clone_id}", headers=student_headers).json()
    assert clone["answer_format"] == "multi_step" and len(clone["parts"][0]["steps"]) == 4

    url = f"{BASE}/{clone_id}/submit"
    part_id = clone["parts"][0]["id"]
    assert client.post(url, headers=student_headers, json={"part_id": part_id, "step_answers": WRONG_R1}).status_code == 200
    me = client.get("/api/v1/auth/me", headers=student_headers).json()
    score = lambda: client.get(f"/api/v1/assessments/{a['id']}/students/{me['id']}/component-scores",  # noqa: E731
                               headers=staff_headers).json()["total_weighted_score"]
    assert score() == 70.0
    # A worse attempt later doesn't lower it: the best one counts.
    client.post(url, headers=student_headers, json={"part_id": part_id, "step_answers": ["", "", "", "STUDENT"]})
    assert score() == 70.0

    details = client.get(f"/api/v1/ra/analytics/questions/{clone_id}", headers=staff_headers).json()
    [row] = details["parts"]
    assert [(s["reached"], s["carried"], s["missed"]) for s in row["steps"]] == [(0, 0, 1), (1, 0, 0), (1, 1, 0),
                                                                                  (1, 1, 0)]
    student = next(s for s in details["students"] if s["user_id"] == me["id"])
    assert student["marks_earned"] == 7 and student["marks_total"] == 10
