from types import SimpleNamespace

from app.core.normalization.fd_engine import FD
from app.core.normalization.fd_exercises import COURSE_REGISTRATION_FD
from app.services.normalization.fd_service import evaluate_fd_attempt
from app.services.normalization.submissions import partial_fd_percent


def approved_fds() -> list[FD]:
    return list(COURSE_REGISTRATION_FD.approved_model_fds)


def test_equivalent_fd_sets_receive_full_credit() -> None:
    result, semantic = evaluate_fd_attempt(
        attempt_id="equivalent",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=approved_fds(),
        assumption="",
        semantic_judge=None,
    )
    assert result.decision == "accepted"
    assert result.decision_source == "deterministic_equivalence"
    assert result.formal_evidence.logically_equivalent is True
    assert semantic is None


def test_partial_fd_percent_uses_balanced_coverage_and_soundness() -> None:
    result = SimpleNamespace(
        decision="rejected",
        formal_evidence=SimpleNamespace(reference_coverage=0.5, submission_soundness=1.0),
    )
    assert partial_fd_percent(result) == 67


def test_sample_contradiction_rejects_and_exposes_conflicting_rows() -> None:
    result, semantic = evaluate_fd_attempt(
        attempt_id="contradiction",
        exercise=COURSE_REGISTRATION_FD,
        submitted_fds=[FD(frozenset({"CourseID"}), frozenset({"Grade"}))],
        assumption="",
        semantic_judge=None,
    )
    contradiction = result.formal_evidence.sample_contradictions[0]
    assert result.decision == "rejected"
    assert result.decision_source == "sample_contradiction"
    assert contradiction.first_values["CourseID"] == contradiction.second_values["CourseID"]
    assert contradiction.first_values["Grade"] != contradiction.second_values["Grade"]
    assert semantic is None
