"""Application orchestration for Phase 1 FD submission evaluation."""

from __future__ import annotations

from app.core.normalization.fd_engine import (
    FD,
    canonicalize,
    logically_equivalent,
    non_trivial,
    partial_overlap,
    sample_contradictions,
    validate_domain,
)
from app.core.normalization.fd_exercises import FDExercise
from app.core.normalization.schemas import (
    FDContradictionResponse,
    FDFormalEvidenceResponse,
    FDSemanticEvidenceResponse,
    FDSubmissionResult,
)
from .semantic_judge import (
    SemanticFD,
    SemanticJudge,
    SemanticJudgeError,
    SemanticReviewRequest,
    SemanticReviewResult,
)


ENGINE_VERSION = "fd-engine-1.0"


def evaluate_fd_attempt(
    *,
    attempt_id: str,
    exercise: FDExercise,
    submitted_fds: list[FD],
    assumption: str,
    semantic_judge: SemanticJudge | None,
    semantic_review_enabled: bool = True,
) -> tuple[FDSubmissionResult, SemanticReviewResult | None]:
    attributes = frozenset(exercise.attributes)
    canonical_submitted = canonicalize(submitted_fds)
    validate_domain(canonical_submitted, attributes)

    overlap = partial_overlap(canonical_submitted, exercise.approved_model_fds)
    equivalent = logically_equivalent(
        canonical_submitted, exercise.approved_model_fds
    )
    contradictions = sample_contradictions(
        canonical_submitted, list(exercise.sample_rows)
    )
    formal_evidence = FDFormalEvidenceResponse(
        logically_equivalent=equivalent,
        reference_coverage=overlap.reference_coverage,
        submission_soundness=overlap.submission_soundness,
        reference_matched=overlap.reference_matched,
        reference_total=overlap.reference_total,
        submission_matched=overlap.submission_matched,
        submission_total=overlap.submission_total,
        sample_contradictions=[
            FDContradictionResponse(
                lhs=sorted(item.fd.lhs),
                rhs=sorted(item.fd.rhs),
                first_row=item.first_row,
                second_row=item.second_row,
            )
            for item in contradictions
        ],
    )

    result_base = {
        "attempt_id": attempt_id,
        "exercise_id": exercise.id,
        "exercise_version": exercise.version,
        "formal_evidence": formal_evidence,
    }
    if equivalent:
        return (
            FDSubmissionResult(
                **result_base,
                decision="accepted",
                decision_source="deterministic_equivalence",
                can_proceed=True,
                feedback=(
                    "Your functional dependencies are logically equivalent to the "
                    "approved interpretation."
                ),
            ),
            None,
        )

    if contradictions:
        row_pairs = ", ".join(
            f"rows {item.first_row} and {item.second_row}" for item in contradictions
        )
        return (
            FDSubmissionResult(
                **result_base,
                decision="rejected",
                decision_source="sample_contradiction",
                can_proceed=False,
                feedback=(
                    "At least one submitted dependency is contradicted by the sample "
                    f"data ({row_pairs}). Revise the determinant or dependent attributes."
                ),
            ),
            None,
        )

    if not non_trivial(canonical_submitted):
        return (
            FDSubmissionResult(
                **result_base,
                decision="rejected",
                decision_source="trivial_only",
                can_proceed=False,
                feedback=(
                    "The submission contains only trivial dependencies. Add dependencies "
                    "that express how different relation attributes determine one another."
                ),
            ),
            None,
        )

    if not semantic_review_enabled:
        return (
            FDSubmissionResult(
                **result_base,
                decision="rejected",
                decision_source="semantic_review_disabled",
                can_proceed=False,
                feedback=(
                    "This exercise currently accepts FD sets that are logically "
                    "equivalent to the approved interpretation. Revise the FD set "
                    "and submit again."
                ),
            ),
            None,
        )

    if semantic_judge is None:
        return _provider_failure_result(result_base), None

    try:
        semantic_result = semantic_judge.review(
            SemanticReviewRequest(
                exercise_id=exercise.id,
                exercise_version=exercise.version,
                scenario=exercise.scenario,
                statements=[
                    f"{statement.id}: {statement.text}"
                    for statement in exercise.statements
                ],
                sample_rows=[dict(row) for row in exercise.sample_rows],
                student_fds=[
                    SemanticFD(lhs=sorted(fd.lhs), rhs=sorted(fd.rhs))
                    for fd in canonical_submitted
                ],
                assumption=assumption,
                approved_model_fds=[
                    SemanticFD(lhs=sorted(fd.lhs), rhs=sorted(fd.rhs))
                    for fd in canonicalize(exercise.approved_model_fds)
                ],
                deterministic_evidence=formal_evidence.model_dump(mode="json"),
            )
        )
    except SemanticJudgeError:
        return _provider_failure_result(result_base), None

    verdict = semantic_result.decision.decision
    decision = "accepted" if verdict == "accept" else "rejected" if verdict == "reject" else "staff_review"
    return (
        FDSubmissionResult(
            **result_base,
            decision=decision,
            decision_source="semantic_review",
            can_proceed=decision == "accepted",
            feedback=semantic_result.decision.student_feedback,
            semantic_evidence=FDSemanticEvidenceResponse(
                verdict=verdict,
                provider=semantic_result.provider,
                model=semantic_result.model,
                response_id=semantic_result.response_id,
            ),
        ),
        semantic_result,
    )


def _provider_failure_result(result_base: dict[str, object]) -> FDSubmissionResult:
    return FDSubmissionResult(
        **result_base,
        decision="staff_review",
        decision_source="provider_failure",
        can_proceed=False,
        feedback=(
            "The interpretation could not be reviewed automatically. Your attempt has "
            "been preserved for staff review."
        ),
    )
