from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest

from app.models.assessment import Assessment
from app.models.assessment_item import AssessmentItem
from app.models.assessment_session import AssessmentSession
from app.models.normalization import NormalizationQuestion, NormalizationSubmission
from app.models.user import User
from app.services import assessment_clone, assessment_scoring
from app.services.normalization import submissions
from app.services.normalization.semantic_judge import SemanticReviewResult, SemanticReviewDecision
from scripts.import_normalization_starters import import_starters

BASE = "/api/v1/normalization"


def question_input(**overrides):
    return {"title": "Independent normalization", "difficulty": "easy", "scenario": "Each A identifies one B.",
            "relation_name": "R", "attributes": ["A", "B"], "statements": [{"id": "S1", "text": "Each A identifies one B."}],
            "sample_rows": [{"A": "1", "B": "x"}, {"A": "2", "B": "y"}],
            "target_normal_form": "BCNF", "approved_fds": [{"lhs": ["A"], "rhs": ["B"]}], **overrides}


def create(api, publish=True, **overrides):
    client, h, _ = api
    response = client.post(f"{BASE}/questions", headers=h["staff"], json=question_input(**overrides))
    assert response.status_code == 201, response.text
    q = response.json()
    if publish:
        response = client.post(f"{BASE}/questions/{q['id']}/publish", headers=h["staff"])
        assert response.status_code == 200, response.text
    return q


def payload(q, **overrides):
    relation = {"name": "Any name", "attributes": ["A", "B"], "primary_key": ["A"]}
    return {"exercise_id": str(q["id"]), "exercise_version": str(q["version"]), "target_normal_form": "BCNF",
            "functional_dependencies": [{"lhs": ["A"], "rhs": ["B"]}], "assumption": "",
            "relations": [relation], "process": {"workflow": "recursive_decomposition", "root": {"node_id": "root", **relation}, "steps": []},
            "canvas_positions": [{"node_id": "root", "x": 20, "y": 40}], "request_key": str(uuid4()), **overrides}


def send(api, q, body=None):
    client, h, _ = api
    response = client.post(f"{BASE}/questions/{q['id']}/submissions", headers=h["student"], json=body or payload(q))
    assert response.status_code == 200, response.text
    return response.json()


def test_health_auth_roles_and_private_answers(api):
    client, h, _ = api
    assert client.get("/health").status_code == 200
    assert client.get(f"{BASE}/questions").status_code == 401
    assert client.post(f"{BASE}/questions", headers=h["student"], json=question_input()).status_code == 403
    q = create(api, publish=False)
    assert client.get(f"{BASE}/questions", headers=h["student"]).json() == []
    assert client.get(f"{BASE}/questions/{q['id']}", headers=h["student"]).status_code == 404
    client.post(f"{BASE}/questions/{q['id']}/publish", headers=h["admin"])
    public = client.get(f"{BASE}/questions/{q['id']}", headers=h["student"]).json()
    assert "approved_fds" not in public
    assert public["semantic_judge_enabled"] is False
    assert client.get(f"{BASE}/questions/{q['id']}/authoring", headers=h["student"]).status_code == 403


def test_public_question_exposes_only_semantic_prompt_toggle(api, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "NORMALIZATION_SEMANTIC_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setattr(settings, "NORMALIZATION_SEMANTIC_MODEL", "test-only")
    q = create(api, semantic_judge_enabled=True)
    client, h, _ = api
    for public in (client.get(f"{BASE}/questions/{q['id']}", headers=h["student"]).json(),
                   client.get(f"{BASE}/questions", headers=h["student"]).json()[0]):
        assert public["semantic_judge_enabled"] is True
        assert "approved_fds" not in public
        assert "engine_versions" not in public


def test_migration_adds_shared_tables_without_changing_existing_records(api, monkeypatch):
    from sqlalchemy import inspect
    from app.models.normalization import NormalizationReview
    import run_normalization_migration as migration

    client, headers, sessions = api
    with sessions() as db:
        users_before = [(user.id, user.email, user.role) for user in db.query(User).order_by(User.id)]
        staff_id = next(user.id for user in db.query(User) if user.role.value == "staff")
        existing = Assessment(title="Existing assessment survives migration", created_by=staff_id)
        db.add(existing)
        db.commit()
        assessment_id = existing.id
        shared_engine = db.get_bind()

    # Only this fixture's isolated schema is changed, never a configured project DB.
    for model in (NormalizationReview, NormalizationSubmission, NormalizationQuestion):
        model.__table__.drop(shared_engine)
    monkeypatch.setattr(migration, "engine", shared_engine)
    migration.main()
    migration.main()

    with sessions() as db:
        assert [(user.id, user.email, user.role) for user in db.query(User).order_by(User.id)] == users_before
        assert db.get(Assessment, assessment_id).title == "Existing assessment survives migration"
    inspector = inspect(shared_engine)
    assert {fk["referred_table"] for fk in inspector.get_foreign_keys("normalization_questions")} == {"users", "assessments"}
    assert {fk["referred_table"] for fk in inspector.get_foreign_keys("normalization_submissions")} == {"users", "normalization_questions"}
    q = create(api)
    assert send(api, q)["result"]["score"]["overall_percent"] == 100


def test_equivalent_submission_history_ownership_and_progress(api):
    client, h, _ = api
    q = create(api)
    attempt = send(api, q)
    assert datetime.fromisoformat(attempt["created_at"].replace("Z", "+00:00")).tzinfo is not None
    assert attempt["result"]["decision"] == "accepted"
    assert attempt["result"]["score"] == {"fd_percent": 100, "normalization_percent": 100, "overall_percent": 100}
    assert "snapshot" not in attempt and "semantic_evidence" not in attempt
    assert client.get(f"{BASE}/submissions/{attempt['id']}", headers=h["other"]).status_code == 404
    assert client.get(f"{BASE}/questions/{q['id']}/submissions", headers=h["other"]).json() == []
    assert client.get(f"{BASE}/progress", headers=h["student"]).json()[0]["completed"]
    assert client.get(f"{BASE}/progress", headers=h["other"]).json()[0]["attempt_count"] == 0


def test_idempotency_and_preview_do_not_duplicate_activity(api):
    client, h, sessions = api
    q = create(api)
    body = payload(q)
    a = send(api, q, body)
    assert send(api, q, body)["id"] == a["id"]
    changed = {**body, "assumption": "Changed"}
    assert client.post(f"{BASE}/questions/{q['id']}/submissions", headers=h["student"], json=changed).status_code == 409
    assert client.post(f"{BASE}/questions/{q['id']}/preview", headers=h["staff"], json=body).status_code == 200
    assert client.post(f"{BASE}/questions/{q['id']}/submissions", headers=h["staff"], json=body).status_code == 403
    with sessions() as db:
        assert db.query(NormalizationSubmission).count() == 1


def test_hidden_feedback_applies_to_every_student_read(api):
    client, h, _ = api
    q = create(api, hide_correctness=True)
    attempt = send(api, q)
    for value in (attempt, client.get(f"{BASE}/submissions/{attempt['id']}", headers=h["student"]).json(),
                  client.get(f"{BASE}/questions/{q['id']}/submissions", headers=h["student"]).json()[0]):
        assert value["feedback_hidden"] and value["result"] is None and value["reviews"] == []
        assert value["status"] == "submitted" and "snapshot" not in value
    progress = client.get(f"{BASE}/progress", headers=h["student"]).json()[0]
    assert progress["best_score"] is None and not progress["completed"]
    assert client.post(f"{BASE}/submissions/{attempt['id']}/review-request", headers=h["student"], json={"reason": "Explain"}).status_code == 409
    assert client.get(f"{BASE}/submissions/{attempt['id']}", headers=h["staff"]).json()["result"]["score"]["overall_percent"] == 100


def test_versioned_edits_and_immutable_snapshot(api):
    client, h, _ = api
    q = create(api)
    attempt = send(api, q)
    update = question_input(version=q["version"], title="Edited title")
    assert client.put(f"{BASE}/questions/{q['id']}", headers=h["staff"], json=update).status_code == 200
    assert client.put(f"{BASE}/questions/{q['id']}", headers=h["staff"], json=update).status_code == 409
    assert client.post(f"{BASE}/questions/{q['id']}/submissions", headers=h["student"], json=payload(q)).status_code == 409
    original = client.get(f"{BASE}/submissions/{attempt['id']}", headers=h["staff"]).json()
    assert original["snapshot"]["title"] == q["title"]
    assert client.delete(f"{BASE}/questions/{q['id']}", headers=h["staff"]).status_code == 204
    assert client.get(f"{BASE}/submissions/{attempt['id']}", headers=h["student"]).status_code == 200


def test_reference_contradictions_and_unconfigured_ai_block_publication(api):
    client, h, _ = api
    invalid = question_input(sample_rows=[{"A": "1", "B": "x"}, {"A": "1", "B": "y"}])
    assert client.post(f"{BASE}/questions", headers=h["staff"], json=invalid).status_code == 422
    q = create(api, publish=False, semantic_judge_enabled=True)
    assert client.post(f"{BASE}/questions/{q['id']}/publish", headers=h["staff"]).status_code == 422
    invalid = question_input(attributes=[str(n) for n in range(9)])
    assert client.post(f"{BASE}/questions", headers=h["staff"], json=invalid).status_code == 422


def test_ai_toggle_and_provider_failure_are_question_scoped(api, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "NORMALIZATION_SEMANTIC_API_KEY", "test-key")
    monkeypatch.setattr(settings, "NORMALIZATION_SEMANTIC_MODEL", "test-model")
    calls = []
    class Judge:
        def __init__(self, **kwargs): pass
        def close(self): pass
        def review(self, request):
            calls.append(request)
            return SemanticReviewResult(decision=SemanticReviewDecision(decision="accept", rationale="Supported", student_feedback="Supported", referenced_statement_ids=["S1"]), provider="fake", model="test", response_id="test")
    monkeypatch.setattr(submissions, "OpenAISemanticJudge", Judge)
    q = create(api, semantic_judge_enabled=True)
    assert send(api, q)["result"]["decision"] == "accepted"
    assert not calls
    wrong = [{"lhs": ["B"], "rhs": ["A"]}]
    assert send(api, q, payload(q, functional_dependencies=wrong))["result"]["fd_evaluation"]["decision"] == "accepted"
    assert len(calls) == 1
    off = create(api)
    assert send(api, off, payload(off, functional_dependencies=wrong))["result"]["fd_evaluation"]["decision_source"] == "semantic_review_disabled"
    assert len(calls) == 1
    monkeypatch.setattr(settings, "NORMALIZATION_SEMANTIC_API_KEY", "")
    assert send(api, q, payload(q, functional_dependencies=wrong))["result"]["decision"] == "staff_review"


def test_staff_review_preserves_formal_grade_and_is_version_checked(api):
    client, h, _ = api
    q = create(api)
    a = send(api, q, payload(q, functional_dependencies=[{"lhs": ["B"], "rhs": ["A"]}]))
    normal = a["result"]["score"]["normalization_percent"]
    original = deepcopy(a["result"])
    assert client.post(f"{BASE}/submissions/{a['id']}/review-request", headers=h["student"], json={"reason": "Business rule interpretation"}).status_code == 200
    body = {"decision": "accepted", "reason": "Alternative interpretation is supported", "version": 0}
    assert client.post(f"{BASE}/submissions/{a['id']}/review", headers=h["student"], json=body).status_code == 403
    response = client.post(f"{BASE}/submissions/{a['id']}/review", headers=h["staff"], json=body)
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["original_result"] == original
    assert reviewed["result"]["score"]["fd_percent"] == 100
    assert reviewed["result"]["score"]["normalization_percent"] == normal
    assert client.post(f"{BASE}/submissions/{a['id']}/review", headers=h["admin"], json=body).status_code == 409


def test_semantic_review_cannot_accept_a_deterministic_contradiction(api):
    client, h, _ = api
    q = create(api, sample_rows=[{"A": "1", "B": "x"}, {"A": "2", "B": "x"}])
    a = send(api, q, payload(q, functional_dependencies=[{"lhs": ["B"], "rhs": ["A"]}]))
    assert a["result"]["fd_evaluation"]["decision_source"] == "sample_contradiction"
    result = client.post(f"{BASE}/submissions/{a['id']}/review", headers=h["staff"], json={
        "decision": "accepted", "reason": "Semantic interpretation", "version": 0})
    assert result.status_code == 422


def assessment_for(api, q, hidden=False):
    client, h, _ = api
    a = client.post("/api/v1/assessments", headers=h["staff"], json={"title": "Mixed assessment", "items": [
        {"item_type": "normalization_question", "item_id": q["id"], "weight": 100, "hide_correctness": hidden}]}).json()
    response = client.post(f"/api/v1/assessments/{a['id']}/publish", headers=h["staff"])
    assert response.status_code == 200, response.text
    detail = client.get(f"/api/v1/assessments/{a['id']}", headers=h["staff"]).json()
    return a["id"], detail["items"][0]["item_id"]


def test_assessment_clones_access_best_score_and_finalized_review(api):
    client, h, sessions = api
    q = create(api)
    aid, clone = assessment_for(api, q)
    assert clone != q["id"]
    assert client.get(f"{BASE}/questions/{clone}", headers=h["student"]).status_code in (403, 404)
    client.post(f"/api/v1/assessments/{aid}/start", headers=h["staff"])
    assert client.post(f"/api/v1/student-assessments/{aid}/join", headers=h["student"], json={}).status_code == 200
    cq = {**q, "id": clone}
    a = send(api, cq)
    client.post(f"/api/v1/student-assessments/{aid}/session/submit", headers=h["student"])
    with sessions() as db:
        session = db.query(AssessmentSession).filter_by(assessment_id=aid).one()
        assert session.weighted_score == 100
    r = client.post(f"{BASE}/submissions/{a['id']}/review", headers=h["staff"], json={"decision": "rejected", "reason": "Rejected interpretation", "version": 0})
    assert r.status_code == 200, r.text
    with sessions() as db:
        assert db.query(AssessmentSession).filter_by(assessment_id=aid).one().weighted_score == 50
    assert client.post(f"{BASE}/questions/{clone}/submissions", headers=h["student"], json=payload(cq)).status_code == 403
    report = client.get(f"/api/v1/assessments/{aid}/students", headers=h["staff"])
    assert report.status_code == 200
    # A reset removes only clone attempts; unrelated practice remains.
    practice = send(api, q)
    assert client.post(f"/api/v1/assessments/{aid}/students/{a['user_id']}/reset", headers=h["staff"]).status_code == 200
    assert client.get(f"{BASE}/submissions/{a['id']}", headers=h["staff"]).status_code == 404
    assert client.get(f"{BASE}/submissions/{practice['id']}", headers=h["student"]).status_code == 200


def test_starters_are_drafts_and_idempotent(api):
    _, _, sessions = api
    with sessions() as db:
        owner = db.query(User).filter_by(email="staff@normalization.test").one()
        assert import_starters(db, owner.id) == 6
        assert import_starters(db, owner.id) == 0
        assert db.query(NormalizationQuestion).filter_by(is_published=1).count() == 0


def test_migration_reruns_without_changing_content(api, monkeypatch):
    import run_normalization_migration
    _, _, sessions = api
    q = create(api)
    with sessions() as db:
        monkeypatch.setattr(run_normalization_migration, "engine", db.get_bind())
        run_normalization_migration.main()
        run_normalization_migration.main()
        assert db.get(NormalizationQuestion, q["id"]).title == q["title"]


def test_assessment_hidden_setting_and_frozen_content(api):
    client, h, sessions = api
    q = create(api)
    aid, clone_id = assessment_for(api, q, hidden=True)
    update = question_input(version=q["version"], title="Bank changed", target_normal_form="3NF")
    assert client.put(f"{BASE}/questions/{q['id']}", headers=h["staff"], json=update).status_code == 200
    with sessions() as db:
        clone = db.get(NormalizationQuestion, clone_id)
        assert clone.title == q["title"] and clone.target_normal_form == "BCNF"
        assert clone.hide_correctness == 1
    client.post(f"/api/v1/assessments/{aid}/start", headers=h["staff"])
    client.post(f"/api/v1/student-assessments/{aid}/join", headers=h["student"], json={})
    attempt = send(api, {**q, "id": clone_id})
    assert attempt["result"] is None
    assert all(row["id"] != clone_id for row in client.get(f"{BASE}/questions", headers=h["staff"]).json())
    assert client.put(f"{BASE}/questions/{clone_id}", headers=h["staff"], json=question_input(version=q["version"])).status_code == 409


def test_expiry_and_gateway_checks_prevent_new_attempts(api):
    client, h, sessions = api
    q = create(api)
    aid, clone_id = assessment_for(api, q)
    client.post(f"/api/v1/assessments/{aid}/start", headers=h["staff"])
    client.post(f"/api/v1/student-assessments/{aid}/join", headers=h["student"], json={})
    with sessions() as db:
        a = db.get(Assessment, aid)
        a.gateway_enabled = 1
        db.commit()
    assert client.get(f"{BASE}/questions/{clone_id}", headers=h["student"]).status_code == 403
    with sessions() as db:
        db.get(Assessment, aid).gateway_enabled = 0
        session = db.query(AssessmentSession).filter_by(assessment_id=aid).one()
        session.end_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.post(f"{BASE}/questions/{clone_id}/submissions", headers=h["student"], json=payload({**q, "id": clone_id})).status_code == 403
    with sessions() as db:
        assert db.query(NormalizationSubmission).count() == 0
        assert db.query(AssessmentSession).filter_by(assessment_id=aid).one().attempt_complete


def test_grading_after_finalization_refreshes_the_frozen_score(api, monkeypatch):
    from app.services.assessment_timer import finalize_session
    client, h, sessions = api
    q = create(api)
    aid, clone_id = assessment_for(api, q)
    client.post(f"/api/v1/assessments/{aid}/start", headers=h["staff"])
    client.post(f"/api/v1/student-assessments/{aid}/join", headers=h["student"], json={})
    evaluate = submissions.evaluate
    def delayed(*args):
        with sessions() as db:
            session = db.query(AssessmentSession).filter_by(assessment_id=aid).one()
            finalize_session(db, session)
            assert session.weighted_score == 0
        return evaluate(*args)
    monkeypatch.setattr(submissions, "evaluate", delayed)
    send(api, {**q, "id": clone_id})
    with sessions() as db:
        session = db.query(AssessmentSession).filter_by(assessment_id=aid).one()
        assert session.attempt_complete and session.weighted_score == 100


def test_best_score_analytics_and_requested_reviews(api):
    client, h, _ = api
    q = create(api)
    aid, clone_id = assessment_for(api, q)
    client.post(f"/api/v1/assessments/{aid}/start", headers=h["staff"])
    client.post(f"/api/v1/student-assessments/{aid}/join", headers=h["student"], json={})
    clone = {**q, "id": clone_id}
    accepted = send(api, clone)
    send(api, clone, payload(clone, functional_dependencies=[{"lhs": ["B"], "rhs": ["A"]}]))
    report = client.get(f"/api/v1/assessments/{aid}/item-analytics", headers=h["staff"])
    assert report.status_code == 200, report.text
    item = report.json()["items"][0]
    assert item["avg_score_fraction"] == 1 and item["correct_count"] == 1
    assert item["total_attempts"] == 2
    client.post(f"{BASE}/submissions/{accepted['id']}/review-request", headers=h["student"], json={"reason": "Please explain"})
    assert client.get(f"{BASE}/questions/{clone_id}/analytics", headers=h["staff"]).json()["review_pending"] == 1


def test_concurrent_retry_and_finalize_on_postgres(api, monkeypatch):
    import os
    import pytest
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    if not os.environ.get("NORMALIZATION_TEST_POSTGRES_URL"):
        pytest.skip("True concurrent transactions require the PostgreSQL test runner")
    client, h, sessions = api
    q = create(api)
    aid, clone_id = assessment_for(api, q)
    client.post(f"/api/v1/assessments/{aid}/start", headers=h["staff"])
    client.post(f"/api/v1/student-assessments/{aid}/join", headers=h["student"], json={})
    entered, release = Event(), Event()
    evaluate = submissions.evaluate
    def delayed(*args):
        entered.set()
        assert release.wait(15)
        return evaluate(*args)
    monkeypatch.setattr(submissions, "evaluate", delayed)
    clone = {**q, "id": clone_id}
    body = payload(clone)
    with ThreadPoolExecutor(max_workers=1) as workers:
        future = workers.submit(send, api, clone, body)
        try:
            assert entered.wait(10)
            retry = send(api, clone, body)
            assert retry["status"] == "processing"
            finished = client.post(f"/api/v1/student-assessments/{aid}/session/submit", headers=h["student"])
            assert finished.status_code == 200, finished.text
        finally:
            release.set()
        completed = future.result(timeout=15)
        assert completed["id"] == retry["id"]
    with sessions() as db:
        assert db.query(NormalizationSubmission).count() == 1
        assert db.query(AssessmentSession).filter_by(assessment_id=aid).one().weighted_score == 100


def test_sql_and_erd_authoring_and_sql_execution_still_work(api):
    client, h, _ = api
    sql = client.post("/api/v1/questions", headers=h["staff"], json={"title": "SQL regression", "description": "Select one", "difficulty": "easy",
        "schema_sql": "CREATE TABLE t (id INTEGER);", "sample_data_sql": "INSERT INTO t VALUES (1);", "correct_answer_query": "SELECT id FROM t"})
    assert sql.status_code == 201, sql.text
    qid = sql.json()["id"]
    assert client.post(f"/api/v1/questions/{qid}/publish", headers=h["staff"]).status_code == 200
    result = client.post("/api/v1/execute", headers=h["student"], json={"question_id": qid, "query": "SELECT id FROM t"})
    assert result.status_code == 200, result.text
    assert result.json()["is_correct"]
    erd = client.post("/api/v1/er-diagram/questions", headers=h["staff"], data={"title": "ERD regression", "problem_statement": "An entity", "notation": "Chen",
        "difficulty_label": "Easy", "difficulty_rationale": "One entity", "rubric_md": "Entity 1 mark", "rubric_json": "{}", "instruction_history": "[]"})
    assert erd.status_code == 201, erd.text
    eid = erd.json()["id"]
    assert client.post(f"/api/v1/er-diagram/questions/{eid}/publish", headers=h["staff"]).status_code == 200
    assert client.get(f"/api/v1/er-diagram/questions/{eid}", headers=h["student"]).status_code == 200


@pytest.mark.parametrize("lab_type", ["sql", "graph"])
def test_database_labs_still_run_in_mixed_normalization_assessments(api, lab_type):
    from app.models.lab_session import LabSession
    client, h, sessions = api
    if lab_type == "sql":
        schema, data, query = "CREATE TABLE t (id INTEGER);", "INSERT INTO t VALUES (1);", "SELECT id FROM t"
    else:
        schema, data, query = "CREATE (:Person {name: 'One'});", "CREATE (:Person {name: 'Two'});", "MATCH (n:Person) RETURN n.name AS name"
    response = client.post("/api/v1/labs", headers=h["staff"], json={"title": "Lab regression", "description": "A database lab",
        "schema_sql": schema, "sample_data_sql": data, "lab_type": lab_type})
    assert response.status_code == 201, response.text
    lab_id = response.json()["id"]
    q = create(api)
    response = client.post("/api/v1/assessments", headers=h["staff"], json={"title": "Mixed lab assessment", "items": [
        {"item_type": "normalization_question", "item_id": q["id"], "weight": 50},
        {"item_type": f"{lab_type}_lab", "item_id": lab_id, "weight": 50}]})
    assert response.status_code == 201, response.text
    aid = response.json()["id"]
    assert client.post(f"/api/v1/assessments/{aid}/publish", headers=h["staff"]).status_code == 200
    items = client.get(f"/api/v1/assessments/{aid}", headers=h["staff"]).json()["items"]
    assert client.post(f"/api/v1/assessments/{aid}/start", headers=h["staff"]).status_code == 200
    assert client.post(f"/api/v1/student-assessments/{aid}/join", headers=h["student"], json={}).status_code == 200
    started = client.post(f"/api/v1/labs/{items[1]['item_id']}/session/start", headers=h["student"])
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]
    executed = client.post(f"/api/v1/labs/session/{session_id}/execute", headers=h["student"], json={"query": query})
    assert executed.status_code == 200 and executed.json()["success"], executed.text
    assert executed.json()["row_count"] == (1 if lab_type == "sql" else 2)
    send(api, {**q, "id": items[0]["item_id"]})
    assert client.post(f"/api/v1/student-assessments/{aid}/session/submit", headers=h["student"]).status_code == 200
    with sessions() as db:
        assert db.query(AssessmentSession).filter_by(assessment_id=aid).one().weighted_score == 50
        assert not db.get(LabSession, session_id).is_active
