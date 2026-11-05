"""RA questions inside assessments: publish clones them, students take them under the
assessment's rules, and the assessment's scoring, analytics and reset include them."""
import pytest

from app.database import SessionLocal
from app.models.ra_attempt import RAAttempt
from app.models.ra_question import RAQuestion
from app.models.ra_question_part import RAQuestionPart
from app.services.ra.examples import TUTORIAL_Q1

Q1_II = "R1 := γ MIN(GPA)→MinGPA (STUDENT)\nR2 := STUDENT ⋈ STUDENT.GPA=R1.MinGPA R1\nAnswer := π Sname (R2)"
WRONG = Q1_II.replace("MIN", "MAX")


@pytest.fixture
def running_assessment(client, staff_headers, ra_on):
    """A published, running assessment whose only item is an RA question (max 2 submits)."""
    q = client.post("/api/v1/ra/questions", headers=staff_headers, json={
        "title": "Lowest GPA (exam)", "description": "Find the name(s) of the student(s) with the lowest GPA.",
        "schema_sql": TUTORIAL_Q1["schema_sql"], "parts": [{"model_answer": Q1_II}], "is_published": True,
        "show_step_direction": True, "assessment_step_direction": False}).json()
    a = client.post("/api/v1/assessments", headers=staff_headers, json={
        "title": "RA quiz", "items": [{"item_type": "ra_question", "item_id": q["id"], "weight": 100,
                                      "max_queries": 2}]})
    assert a.status_code == 201, a.text
    aid = a.json()["id"]
    assert client.post(f"/api/v1/assessments/{aid}/publish", headers=staff_headers).status_code == 200
    assert client.post(f"/api/v1/assessments/{aid}/start", headers=staff_headers).status_code == 200
    item = client.get(f"/api/v1/assessments/{aid}", headers=staff_headers).json()["items"][0]
    return {"bank_id": q["id"], "assessment_id": aid, "item": item}


def test_publish_clones_the_question_with_its_test_databases(running_assessment):
    clone_id = running_assessment["item"]["item_id"]
    assert clone_id != running_assessment["bank_id"]
    assert running_assessment["item"]["item_title"] == "Lowest GPA (exam)"
    db = SessionLocal()
    try:
        clone, bank = db.query(RAQuestion).get(clone_id), db.query(RAQuestion).get(running_assessment["bank_id"])
        assert clone.owner_assessment_id == running_assessment["assessment_id"]
        [clone_part] = db.query(RAQuestionPart).filter(RAQuestionPart.question_id == clone_id).all()
        [bank_part] = db.query(RAQuestionPart).filter(RAQuestionPart.question_id == bank.id).all()
        assert clone_part.id != bank_part.id
        assert clone_part.suite_json == bank_part.suite_json  # the same databases for everyone
        assert clone.show_step_direction == 0                 # "in assessments" setting, off
    finally:
        db.close()


def test_clone_is_hidden_until_the_student_joins(client, student_headers, running_assessment):
    clone_id = running_assessment["item"]["item_id"]
    assert client.get(f"/api/v1/ra/questions/{clone_id}", headers=student_headers).status_code == 404
    assert clone_id not in [q["id"] for q in client.get("/api/v1/ra/questions", headers=student_headers).json()]
    join = client.post(f"/api/v1/student-assessments/{running_assessment['assessment_id']}/join",
                       headers=student_headers, json={})
    assert join.status_code == 200, join.text
    q = client.get(f"/api/v1/ra/questions/{clone_id}", headers=student_headers).json()
    assert q["assessment_id"] == running_assessment["assessment_id"]
    assert q["max_submissions"] == 2 and q["parts"][0]["submissions_used"] == 0
    assert q["show_step_direction"] is False


def test_submissions_are_capped_scored_and_reset(client, staff_headers, student_headers, running_assessment):
    aid = running_assessment["assessment_id"]
    clone_id = running_assessment["item"]["item_id"]
    client.post(f"/api/v1/student-assessments/{aid}/join", headers=student_headers, json={})
    url = f"/api/v1/ra/questions/{clone_id}"

    wrong = client.post(f"{url}/submit", headers=student_headers, json={"answer": WRONG}).json()
    assert wrong["grade"]["verdict"] == "wrong_in_general" and wrong["submissions_used"] == 1
    assert all(s["status"] == "none" for s in wrong["grade"]["steps"])      # no direction in the exam
    # Check is not graded, so it never uses up a submission.
    assert client.post(f"{url}/check", headers=student_headers, json={"answer": Q1_II}).json()["ok"]
    right = client.post(f"{url}/submit", headers=student_headers, json={"answer": Q1_II}).json()
    assert right["grade"]["verdict"] == "correct" and right["submissions_used"] == 2
    capped = client.post(f"{url}/submit", headers=student_headers, json={"answer": Q1_II})
    assert capped.status_code == 403 and "maximum" in capped.json()["detail"]

    me = client.get("/api/v1/auth/me", headers=student_headers).json()
    scores = client.get(f"/api/v1/assessments/{aid}/students/{me['id']}/component-scores",
                        headers=staff_headers).json()
    ra_item = next(c for c in scores["items"] if c["item_type"] == "ra_question")
    assert ra_item["has_correct_attempt"] is True and ra_item["attempt_count"] == 2
    assert scores["total_weighted_score"] == 100.0
    analytics = client.get(f"/api/v1/assessments/{aid}/item-analytics", headers=staff_headers).json()
    row = next(i for i in analytics["items"] if i["item_type"] == "ra_question")
    assert row["item_title"] == "Lowest GPA (exam)" and row["total_attempts"] >= 2

    reset = client.post(f"/api/v1/assessments/{aid}/students/{me['id']}/reset", headers=staff_headers)
    assert reset.status_code == 200 and reset.json()["deleted"]["ra_questions"] == 2
    db = SessionLocal()
    try:
        assert db.query(RAAttempt).filter(RAAttempt.question_id == clone_id, RAAttempt.user_id == me["id"]).count() == 0
    finally:
        db.close()


def test_editing_the_bank_question_leaves_the_exam_copy_alone(client, staff_headers, running_assessment):
    bank = running_assessment["bank_id"]
    body = client.get(f"/api/v1/ra/questions/{bank}/edit", headers=staff_headers).json()
    body["parts"][0]["model_answer"] = "π Sname STUDENT"
    body["title"] = "Edited later"
    assert client.put(f"/api/v1/ra/questions/{bank}", headers=staff_headers, json=body).status_code == 200
    clone = client.get(f"/api/v1/ra/questions/{running_assessment['item']['item_id']}/edit", headers=staff_headers).json()
    assert clone["parts"][0]["model_answer"] == Q1_II and clone["title"] == "Lowest GPA (exam)"


Q1_I = "R1 := σ Numphds < 50 (DEPT)\nAnswer := π Pname (PROF ⋈ R1)"


def test_parts_earn_their_own_marks(client, staff_headers, student_headers, ra_on):
    """A two-part question worth 1 + 3 marks: solving only part (ii) scores 75%, and each
    part has its own submission cap."""
    q = client.post("/api/v1/ra/questions", headers=staff_headers, json={
        "title": "University (2 parts)", "description": "Answer both parts.", "schema_sql": TUTORIAL_Q1["schema_sql"],
        "is_published": True, "parts": [{"label": "(i)", "marks": 1, "model_answer": Q1_I},
                                         {"label": "(ii)", "marks": 3, "model_answer": Q1_II}]}).json()
    a = client.post("/api/v1/assessments", headers=staff_headers, json={
        "title": "RA parts quiz", "items": [{"item_type": "ra_question", "item_id": q["id"], "weight": 100,
                                            "max_queries": 1}]}).json()
    client.post(f"/api/v1/assessments/{a['id']}/publish", headers=staff_headers)
    client.post(f"/api/v1/assessments/{a['id']}/start", headers=staff_headers)
    clone_id = client.get(f"/api/v1/assessments/{a['id']}", headers=staff_headers).json()["items"][0]["item_id"]
    client.post(f"/api/v1/student-assessments/{a['id']}/join", headers=student_headers, json={})

    clone = client.get(f"/api/v1/ra/questions/{clone_id}", headers=student_headers).json()
    p1, p2 = clone["parts"]
    assert [p["id"] for p in clone["parts"]] != [p["id"] for p in q["parts"]]      # the clone's own parts
    url = f"/api/v1/ra/questions/{clone_id}/submit"
    assert client.post(url, headers=student_headers, json={"answer": Q1_II, "part_id": p2["id"]}).json()["grade"]["verdict"] == "correct"
    assert client.post(url, headers=student_headers, json={"answer": Q1_II, "part_id": p2["id"]}).status_code == 403
    # Part (i) still has its own submission.
    assert client.post(url, headers=student_headers, json={"answer": Q1_II, "part_id": p1["id"]}).status_code == 200

    me = client.get("/api/v1/auth/me", headers=student_headers).json()
    scores = client.get(f"/api/v1/assessments/{a['id']}/students/{me['id']}/component-scores",
                        headers=staff_headers).json()
    assert scores["total_weighted_score"] == 75.0
    analytics = client.get(f"/api/v1/assessments/{a['id']}/item-analytics", headers=staff_headers).json()
    row = next(i for i in analytics["items"] if i["item_type"] == "ra_question")
    assert row["total_attempts"] == 2
