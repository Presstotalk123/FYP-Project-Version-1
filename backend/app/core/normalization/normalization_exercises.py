"""Versioned Phase 2 fixtures kept separate from the Phase 1 FD workspace."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .engine import FD


@dataclass(frozen=True)
class NormalizationExercise:
    id: str
    version: str
    title: str
    scenario: str
    target_normal_form: Literal["3NF", "BCNF"]
    workflow: Literal["recursive_decomposition", "synthesis"]
    relation_name: str
    attributes: tuple[str, ...]
    functional_dependencies: tuple[FD, ...]
    requirements: tuple[str, ...]
    dependency_preservation_required: bool


COURSE_REGISTRATION_BCNF = NormalizationExercise(
    id="course-registration-bcnf",
    version="2026-10-12-v1",
    title="Course Registration — BCNF Decomposition",
    scenario=(
        "A university records course enrolments, the instructor assigned to each "
        "course, each instructor's office, and the grade awarded to each student."
    ),
    target_normal_form="BCNF",
    workflow="recursive_decomposition",
    relation_name="COURSE_REGISTRATION",
    attributes=(
        "StudentID",
        "CourseID",
        "InstructorID",
        "InstructorOffice",
        "Grade",
    ),
    functional_dependencies=(
        FD(frozenset({"StudentID", "CourseID"}), frozenset({"Grade"})),
        FD(frozenset({"CourseID"}), frozenset({"InstructorID"})),
        FD(frozenset({"InstructorID"}), frozenset({"InstructorOffice"})),
    ),
    requirements=(
        "Recursively decompose a relation by selecting a BCNF-violating FD.",
        "Every original attribute must occur in a final relation.",
        "The final decomposition must be lossless and every final relation must satisfy BCNF.",
        "Dependency preservation is reported but is advisory for this BCNF exercise.",
    ),
    dependency_preservation_required=False,
)


RELATION_SYNTHESIS_3NF = NormalizationExercise(
    id="relation-synthesis-3nf",
    version="2026-10-21-v2",
    title="Relation Decomposition — Third Normal Form",
    scenario=(
        "For relation R(A, B, C, D), recursively decompose the relation until every "
        "final relation satisfies Third Normal Form."
    ),
    target_normal_form="3NF",
    workflow="recursive_decomposition",
    relation_name="R",
    attributes=("A", "B", "C", "D"),
    functional_dependencies=(
        FD(frozenset({"A", "B"}), frozenset({"C"})),
        FD(frozenset({"C"}), frozenset({"B"})),
        FD(frozenset({"C"}), frozenset({"D"})),
    ),
    requirements=(
        "Recursively decompose a relation by selecting an FD that violates 3NF.",
        "Every original attribute must occur in a final relation.",
        "Each split must follow the lossless decomposition rule for its selected FD.",
        "The final decomposition must be lossless, dependency preserving, and in 3NF.",
    ),
    dependency_preservation_required=True,
)


NORMALIZATION_EXERCISES = {
    COURSE_REGISTRATION_BCNF.id: COURSE_REGISTRATION_BCNF,
    RELATION_SYNTHESIS_3NF.id: RELATION_SYNTHESIS_3NF,
}


def get_normalization_exercise(exercise_id: str) -> NormalizationExercise | None:
    return NORMALIZATION_EXERCISES.get(exercise_id)
