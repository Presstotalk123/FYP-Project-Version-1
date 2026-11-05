import json

import httpx
import pytest

from app.services.normalization.semantic_judge import (
    OpenAISemanticJudge,
    SemanticFD,
    SemanticJudgeError,
    SemanticReviewRequest,
)


def review_request() -> SemanticReviewRequest:
    return SemanticReviewRequest(
        exercise_id="course-registration-fd",
        exercise_version="v1",
        scenario="A university records enrolments and course teaching assignments.",
        statements=[
            "S1: Each course is taught by exactly one instructor.",
            "S2: A grade is recorded for each student-course enrolment.",
        ],
        sample_rows=[
            {
                "StudentID": "S1",
                "CourseID": "C1",
                "InstructorID": "I1",
                "Grade": "A",
            }
        ],
        student_fds=[SemanticFD(lhs=["CourseID"], rhs=["InstructorID"])],
        assumption="A course has one instructor during the represented term.",
        approved_model_fds=[
            SemanticFD(lhs=["CourseID"], rhs=["InstructorID"])
        ],
        deterministic_evidence={
            "logically_equivalent": False,
            "reference_coverage": 0.5,
            "submission_soundness": 1.0,
            "sample_contradictions": [],
        },
    )


@pytest.mark.parametrize("verdict", ["accept", "reject", "staff_review"])
def test_openai_adapter_requests_structured_non_stored_response(verdict: str) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.openai.com/v1/responses"
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "model": "test-model-2026-01-01",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "decision": verdict,
                                        "rationale": "The stated assumption is supported.",
                                        "student_feedback": "Your interpretation is accepted.",
                                        "referenced_statement_ids": ["S1"],
                                    }
                                ),
                            }
                        ],
                    }
                ],
            },
        )

    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )
    judge = OpenAISemanticJudge(api_key="test-key", model="test-model", client=client)

    original_request = review_request()
    original_evidence = original_request.model_dump(mode="json")
    result = judge.review(original_request)
    assert original_request.model_dump(mode="json") == original_evidence

    assert result.decision.decision == verdict
    assert result.provider == "openai"
    assert result.model == "test-model-2026-01-01"
    assert result.response_id == "resp_test"
    assert captured["authorization"] == "Bearer test-key"

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["store"] is False
    assert payload["tools"] == []
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert payload["text"]["format"]["schema"]["additionalProperties"] is False


def test_openai_adapter_turns_refusal_into_provider_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_refusal",
                "model": "test-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "refusal", "refusal": "Cannot process this request."}
                        ],
                    }
                ],
            },
        )

    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )
    judge = OpenAISemanticJudge(api_key="test-key", model="test-model", client=client)

    with pytest.raises(SemanticJudgeError, match="refused"):
        judge.review(review_request())


def test_openai_adapter_rejects_malformed_structured_output() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_bad",
                "model": "test-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"decision":"accept"}'}
                        ],
                    }
                ],
            },
        )

    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(handler),
    )
    judge = OpenAISemanticJudge(api_key="test-key", model="test-model", client=client)

    with pytest.raises(SemanticJudgeError, match="failed"):
        judge.review(review_request())


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"status": "incomplete", "output": []},
        {"status": "completed", "output": None},
        {"status": "completed", "output": [None]},
        {"status": "completed", "output": [{"content": None}]},
        {"status": "completed", "output": []},
    ],
)
def test_openai_adapter_rejects_unusable_response_envelopes(body: object) -> None:
    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)),
    )
    judge = OpenAISemanticJudge(api_key="test-key", model="test-model", client=client)
    with pytest.raises(SemanticJudgeError):
        judge.review(review_request())


def test_openai_adapter_wraps_timeout_without_returning_acceptance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Test timeout", request=request)

    client = httpx.Client(
        base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handler)
    )
    judge = OpenAISemanticJudge(api_key="test-key", model="test-model", client=client)
    with pytest.raises(SemanticJudgeError, match="failed"):
        judge.review(review_request())


def test_openai_adapter_requires_explicit_environment_configuration(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_SEMANTIC_MODEL", raising=False)
    with pytest.raises(ValueError, match="api_key"):
        OpenAISemanticJudge.from_environment()
