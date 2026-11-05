"""Phase 3 handoff from an accepted FD attempt to normalization."""

from __future__ import annotations

from typing import Literal

from app.core.normalization.engine import FD as NormalizationFD
from app.core.normalization.fd_engine import FD as WorkspaceFD, canonicalize
from app.core.normalization.fd_exercises import FDExercise
from app.core.normalization.normalization_exercises import NormalizationExercise


TargetNormalForm = Literal["3NF", "BCNF"]


def build_handoff_exercise(
    *,
    attempt_id: str,
    source: FDExercise,
    submitted_fds: list[WorkspaceFD],
    target: TargetNormalForm,
) -> NormalizationExercise:
    """Build an immutable normalization exercise from the accepted submission."""
    target_slug = target.casefold()
    dependency_preservation_required = target == "3NF"
    target_rule = (
        "Every final relation must satisfy BCNF."
        if target == "BCNF"
        else "Every final relation must satisfy 3NF."
    )
    preservation_rule = (
        "Dependency preservation is reported but is advisory for BCNF."
        if target == "BCNF"
        else "The final decomposition must preserve the accepted dependencies."
    )
    return NormalizationExercise(
        id=f"course-registration-integrated-{target_slug}",
        version=f"{source.version}-{attempt_id}-{target_slug}-v1",
        title=f"{source.title} — {target} Normalization",
        scenario=(
            f"Continue from accepted FD attempt {attempt_id}. Use the accepted "
            "dependencies as the authoritative input to this normalization task."
        ),
        target_normal_form=target,
        workflow="recursive_decomposition",
        relation_name=source.relation_name,
        attributes=source.attributes,
        functional_dependencies=tuple(
            NormalizationFD(fd.lhs, fd.rhs) for fd in canonicalize(submitted_fds)
        ),
        requirements=(
            f"Recursively decompose a relation by selecting an FD that violates {target}.",
            "Every original attribute must occur in a final relation.",
            "Each split must follow the lossless decomposition rule for its selected FD.",
            target_rule,
            preservation_rule,
        ),
        dependency_preservation_required=dependency_preservation_required,
    )


def build_integrated_exercise(
    *,
    source: FDExercise,
    submitted_fds: list[WorkspaceFD],
    target: TargetNormalForm,
) -> NormalizationExercise:
    """Build the normalization context used by a single combined submission."""
    dependency_preservation_required = target == "3NF"
    return NormalizationExercise(
        id=f"{source.id}-unified-{target.casefold()}",
        version=f"{source.version}-unified-{target.casefold()}-v1",
        title=f"{source.title} — {target}",
        scenario=source.scenario,
        target_normal_form=target,
        workflow="recursive_decomposition",
        relation_name=source.relation_name,
        attributes=source.attributes,
        functional_dependencies=tuple(
            NormalizationFD(fd.lhs, fd.rhs) for fd in canonicalize(submitted_fds)
        ),
        requirements=(
            "Construct the functional dependencies supported by the business rules.",
            f"Recursively decompose the relation until every final relation satisfies {target}.",
            "Every original attribute must occur in a final relation.",
            "Each split must follow the lossless decomposition rule.",
            (
                "Dependency preservation is required."
                if dependency_preservation_required
                else "Dependency preservation is reported but advisory."
            ),
        ),
        dependency_preservation_required=dependency_preservation_required,
    )
