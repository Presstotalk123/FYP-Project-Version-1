"""Staff analytics over RA attempts: per class, per question and part, per student."""
from app.core.security import create_access_token, hash_password
from app.database import SessionLocal
from app.models.user import User, UserRole
from tests.ra.api.test_questions_api import BASE, Q1_I, Q1_II, two_parts

GROUP = "RA-analytics-test"
URL = "/api/v1/ra/analytics"


def student(email):
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == email).first():
            db.add(User(email=email, hashed_password=hash_password("pw"), role=UserRole.STUDENT, class_group=GROUP))
            db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {create_access_token({'sub': email, 'role': 'student'})}"}


def test_analytics_count_students_parts_and_mistakes(client, staff_headers, ra_on):
    q = client.post(BASE, json=two_parts(), headers=staff_headers).json()
    p1, p2 = (p["id"] for p in q["parts"])
    ann, ben = student("ann@ra-analytics.example.com"), student("ben@ra-analytics.example.com")

    def submit(who, part, answer):
        r = client.post(f"{BASE}/{q['id']}/submit", json={"answer": answer, "part_id": part}, headers=who)
        assert r.status_code == 200, r.text

    submit(ann, p1, "π Nope (PROF)")                         # unreadable: unknown attribute
    submit(ann, p2, Q1_II.replace("MIN", "MAX"))             # wrong in general
    submit(ann, p2, Q1_II)                                   # then right
    submit(ben, p1, Q1_I)
    submit(ben, p2, Q1_II)
    submit(staff_headers, p1, Q1_I)                          # staff never count

    c = client.get(URL + "/class", params={"class_group": GROUP}, headers=staff_headers).json()
    assert c["totals"]["students_engaged"] == 2 and c["totals"]["registered_students"] == 2
    assert c["totals"]["submissions"] == 5
    row = next(r for r in c["questions"] if r["question_id"] == q["id"])
    assert (row["parts"], row["students"], row["students_solved"], row["completion_rate"]) == (2, 2, 1, 0.5)
    assert c["verdicts"] == {"correct": 3, "wrong_columns": 0, "wrong_result": 0, "wrong_in_general": 1,
                             "invalid_expression": 1}
    assert [e["code"] for e in c["top_errors"]] == ["RA003"]
    by_email = {s["email"]: s for s in c["students"]}
    assert (by_email["ann@ra-analytics.example.com"]["parts_solved"],
            by_email["ann@ra-analytics.example.com"]["completion_percent"]) == (1, 50)

    d = client.get(f"{URL}/questions/{q['id']}", params={"class_group": GROUP}, headers=staff_headers).json()
    part1, part2 = d["parts"]
    assert (part1["label"], part1["students"], part1["students_solved"], part1["top_errors"][0]["code"]) == \
        ("(i)", 2, 1, "RA003")
    assert (part2["students_solved"], part2["avg_submits_to_correct"]) == (2, 1.5)   # Ann 2, Ben 1
    ann_row = next(s for s in d["students"] if s["email"].startswith("ann"))
    assert (ann_row["marks_earned"], ann_row["marks_total"]) == (3, 4)
    assert [c["last_verdict"] for c in ann_row["parts"]] == ["invalid_expression", "correct"]
    assert d["solved_count"] == 1

    history = client.get(f"{URL}/questions/{q['id']}/students/{ann_row['user_id']}", headers=staff_headers).json()
    assert [(a["part_label"], a["verdict"], a["correct"]) for a in history["attempts"]] == [
        ("(i)", "invalid_expression", False), ("(ii)", "wrong_in_general", False), ("(ii)", "correct", True)]
    assert history["attempts"][0]["error"]["code"] == "RA003"
    assert GROUP in client.get(URL + "/class-groups", headers=staff_headers).json()


def test_analytics_are_for_staff_only(client, student_headers, ra_on):
    assert client.get(URL + "/class", headers=student_headers).status_code == 403
    assert client.get(URL + "/questions/1", headers=student_headers).status_code == 403


def test_analytics_404_while_off(client, staff_headers):
    assert client.get(URL + "/class", headers=staff_headers).status_code == 404
