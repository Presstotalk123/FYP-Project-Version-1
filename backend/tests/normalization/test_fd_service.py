import pytest

from app.core.normalization.fd_engine import FD
from app.core.normalization.fd_exercises import COURSE_REGISTRATION_FD
from app.services.normalization.fd_service import evaluate_fd_attempt
from app.services.normalization.semantic_judge import (
    SemanticReviewDecision,
    SemanticJudgeError,
    SemanticReviewRequest,
    SemanticReviewResult,
)


class FakeJudge:
    def __init__(self, verdict: str = "accept") -> None:
        self.verdict = verdict
        self.calls: list[SemanticReviewRequest] = []

    def review(self, request: SemanticReviewRequest) -> SemanticReviewResult:
        self.calls.append(request)
        return SemanticReviewResult(
            decision=SemanticReviewDecision(
                decision=self.verdict,
                rationale="The wording and assumption support this classification.",
                student_feedback=f"Semantic decision: {self.verdict}.",
                referenced_statement_ids=["S1"],
            ),
            provider="fake",
            model="fake-model",
            response_id="fake-response",
        )


class FailingJudge:
    def review(self, request: SemanticReviewRequest) -> SemanticReviewResult:
        raise SemanticJudgeError("provider unavailable")


def approved_fds() -> list[FD]:
    return list(COURSE_REGISTRATION_FD.approved_model_fds)


def test_equivalent_submission_is_accepted_without_semantic_review() -> None:
    judge = FakeJudge()
    result, semantic = evaluate_fd_attempt(
        attempt_id="attempt-1",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=approved_fds()
        + [
            FD(
                frozenset({"CourseID"}),
                frozenset({"InstructorOffice"}),
            )
        ],
        assumption="",
        semantic_judge=judge,
    )
    assert result.decision == "accepted"
    assert result.decision_source == "deterministic_equivalence"
    assert result.can_proceed is True
    assert result.formal_evidence.logically_equivalent is True
    assert judge.calls == []
    assert semantic is None


def test_sample_contradiction_rejects_without_semantic_review() -> None:
    judge = FakeJudge()
    result, _ = evaluate_fd_attempt(
        attempt_id="attempt-2",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=[
            FD(frozenset({"CourseID"}), frozenset({"Grade"}))
        ],
        assumption="",
        semantic_judge=judge,
    )
    assert result.decision == "rejected"
    assert result.decision_source == "sample_contradiction"
    assert result.formal_evidence.sample_contradictions
    assert judge.calls == []


@pytest.mark.parametrize(
    ("verdict", "expected", "can_proceed"),
    [
        ("accept", "accepted", True),
        ("reject", "rejected", False),
        ("staff_review", "staff_review", False),
    ],
)
def test_non_equivalent_submission_uses_semantic_judge(
    verdict: str, expected: str, can_proceed: bool
) -> None:
    judge = FakeJudge(verdict)
    result, stored = evaluate_fd_attempt(
        attempt_id="attempt-3",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=[
            FD(
                frozenset({"StudentID", "CourseID"}),
                frozenset({"InstructorID"}),
            )
        ],
        assumption="One enrolment uses the course's assigned instructor.",
        semantic_judge=judge,
    )
    assert result.decision == expected
    assert result.can_proceed is can_proceed
    assert result.decision_source == "semantic_review"
    assert result.formal_evidence.logically_equivalent is False
    assert len(judge.calls) == 1
    assert stored is not None


def test_missing_provider_yields_staff_review() -> None:
    result, semantic = evaluate_fd_attempt(
        attempt_id="attempt-4",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=[
            FD(
                frozenset({"StudentID", "CourseID"}),
                frozenset({"InstructorID"}),
            )
        ],
        assumption="",
        semantic_judge=None,
        semantic_review_enabled=True,
    )
    assert result.decision == "staff_review"
    assert result.decision_source == "provider_failure"
    assert result.can_proceed is False
    assert semantic is None


def test_provider_failure_yields_staff_review_without_losing_formal_evidence() -> None:
    result, semantic = evaluate_fd_attempt(
        attempt_id="attempt-provider-failure",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=[
            FD(
                frozenset({"StudentID", "CourseID"}),
                frozenset({"InstructorID"}),
            )
        ],
        assumption="The instructor is inherited from the course.",
        semantic_judge=FailingJudge(),
        semantic_review_enabled=True,
    )
    assert result.decision == "staff_review"
    assert result.decision_source == "provider_failure"
    assert result.can_proceed is False
    assert result.formal_evidence.logically_equivalent is False
    assert result.formal_evidence.submission_total == 1
    assert result.formal_evidence.submission_soundness == 1.0
    assert semantic is None


def test_trivial_only_submission_is_rejected_without_semantic_review() -> None:
    judge = FakeJudge()
    result, _ = evaluate_fd_attempt(
        attempt_id="attempt-5",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=[FD(frozenset({"CourseID"}), frozenset({"CourseID"}))],
        assumption="",
        semantic_judge=judge,
    )
    assert result.decision_source == "trivial_only"
    assert result.formal_evidence.reference_coverage == 0.0
    assert result.formal_evidence.submission_soundness == 0.0
    assert judge.calls == []


def test_disabled_semantic_review_rejects_non_equivalent_without_calling_provider() -> None:
    judge = FakeJudge()
    result, semantic = evaluate_fd_attempt(
        attempt_id="attempt-disabled",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=[
            FD(
                frozenset({"StudentID", "CourseID"}),
                frozenset({"InstructorID"}),
            )
        ],
        assumption="An alternative interpretation.",
        semantic_judge=judge,
        semantic_review_enabled=False,
    )
    assert result.decision == "rejected"
    assert result.decision_source == "semantic_review_disabled"
    assert result.can_proceed is False
    assert judge.calls == []
    assert semantic is None
