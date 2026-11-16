from uuid import uuid4


BASE = "/api/v1/normalization"


def question_input(**overrides):
    return {
        "title": "Scoring policy question",
        "difficulty": "easy",
        "scenario": "Each A identifies one B.",
        "relation_name": "R",
        "attributes": ["A", "B"],
        "statements": [{"id": "S1", "text": "Each A identifies one B."}],
        "sample_rows": [{"A": "1", "B": "x"}, {"A": "2", "B": "y"}],
        "target_normal_form": "BCNF",
        "approved_fds": [{"lhs": ["A"], "rhs": ["B"]}],
        **overrides,
    }


def create(api, **overrides):
    client, headers, _ = api
    response = client.post(f"{BASE}/questions", headers=headers["staff"], json=question_input(**overrides))
    assert response.status_code == 201, response.text
    question = response.json()
    response = client.post(f"{BASE}/questions/{question['id']}/publish", headers=headers["staff"])
    assert response.status_code == 200, response.text
    return question


def payload(question, **overrides):
    relation = {"name": "R", "attributes": ["A", "B"], "primary_key": ["A"]}
    return {
        "exercise_id": str(question["id"]),
        "exercise_version": str(question["version"]),
        "target_normal_form": "BCNF",
        "functional_dependencies": [{"lhs": ["A"], "rhs": ["B"]}],
        "assumption": "",
        "relations": [relation],
        "process": {
            "workflow": "recursive_decomposition",
            "root": {"node_id": "root", **relation},
            "steps": [],
        },
        "canvas_positions": [{"node_id": "root", "x": 20, "y": 40}],
        "request_key": str(uuid4()),
        **overrides,
    }


def send(api, question, body=None):
    client, headers, _ = api
    response = client.post(
        f"{BASE}/questions/{question['id']}/submissions",
        headers=headers["student"],
        json=body or payload(question),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_equivalent_fd_score_is_full_but_untouched_normalization_is_zero(api):
    client, headers, _ = api
    question = create(api)
    attempt = send(api, question)

    assert attempt["result"]["decision"] == "rejected"
    assert attempt["result"]["score"] == {
        "fd_percent": 100,
        "normalization_percent": 0,
        "overall_percent": 50,
        "scoring_policy": "partial_fd_v1",
    }
    assert client.get(f"{BASE}/submissions/{attempt['id']}", headers=headers["student"]).json()["result"]["score"]["overall_percent"] == 50


def test_normalization_credit_requires_valid_workflow(api):
    question = create(api)
    untouched = send(api, question, payload(question))
    assert untouched["result"]["score"]["normalization_percent"] == 0
    assert untouched["result"]["normalization_evaluation"]["normalization_status"] == "not_started"

    invalid_step = {
        "step_id": "invalid",
        "parent_node_id": "root",
        "selected_fd": {"lhs": ["A"], "rhs": ["B"]},
        "children": [
            {"node_id": "left", "name": "AB", "attributes": ["A", "B"], "primary_key": ["A"]},
            {"node_id": "right", "name": "A", "attributes": ["A"], "primary_key": ["A"]},
        ],
    }
    invalid = send(api, question, payload(question, process={
        "workflow": "recursive_decomposition",
        "root": {"node_id": "root", "name": "R", "attributes": ["A", "B"], "primary_key": ["A"]},
        "steps": [invalid_step],
    }))
    assert invalid["result"]["score"]["normalization_percent"] == 0
    assert invalid["result"]["normalization_evaluation"]["normalization_status"] == "invalid"



def test_partial_fd_score_uses_coverage_and_soundness(api):
    question = create(api, approved_fds=[
        {"lhs": ["A"], "rhs": ["B"]},
        {"lhs": ["B"], "rhs": ["A"]},
    ])
    attempt = send(api, question)
    assert attempt["result"]["fd_evaluation"]["formal_evidence"]["reference_coverage"] == 0.5
    assert attempt["result"]["fd_evaluation"]["formal_evidence"]["submission_soundness"] == 1.0
    assert attempt["result"]["score"]["fd_percent"] == 67


def test_staff_rejection_preserves_deterministic_partial_fd_grade(api):
    client, headers, _ = api
    question = create(api, approved_fds=[
        {"lhs": ["A"], "rhs": ["B"]},
        {"lhs": ["B"], "rhs": ["A"]},
    ])
    attempt = send(api, question)
    assert attempt["result"]["score"]["fd_percent"] == 67
    assert client.post(
        f"{BASE}/submissions/{attempt['id']}/review-request",
        headers=headers["student"],
        json={"reason": "Please review the FD interpretation."},
    ).status_code == 200

    response = client.post(
        f"{BASE}/submissions/{attempt['id']}/review",
        headers=headers["staff"],
        json={"decision": "rejected", "reason": "The approved interpretation remains authoritative.", "version": 0},
    )
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed["result"]["decision"] == "rejected"
    assert reviewed["result"]["score"]["fd_percent"] == 67
