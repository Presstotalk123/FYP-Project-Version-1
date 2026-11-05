"""Private Phase 1 exercise definitions.

Student-facing API models are built from these definitions without including
the approved model answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from .fd_engine import FD, validate_approved_answer


@dataclass(frozen=True)
class BusinessStatement:
    id: str
    text: str


@dataclass(frozen=True)
class FDExercise:
    id: str
    version: str
    model_answer_version: str
    title: str
    scenario: str
    relation_name: str
    attributes: tuple[str, ...]
    statements: tuple[BusinessStatement, ...]
    sample_rows: tuple[Mapping[str, object], ...]
    approved_model_fds: tuple[FD, ...]


COURSE_REGISTRATION_FD = FDExercise(
    id="course-registration-fd",
    version="2026-10-08-v1",
    model_answer_version="2026-10-08-answer-v1",
    title="Course Registration Functional Dependencies",
    scenario=(
        "A university stores course enrolments, the instructor assigned to each "
        "course, each instructor's office, and the grade awarded to each student "
        "in a course. Derive the functional dependencies supported by the rules."
    ),
    relation_name="COURSE_REGISTRATION",
    attributes=(
        "StudentID",
        "CourseID",
        "InstructorID",
        "InstructorOffice",
        "Grade",
    ),
    statements=(
        BusinessStatement("S1", "Each course is taught by exactly one instructor."),
        BusinessStatement("S2", "Each instructor is assigned exactly one office."),
        BusinessStatement(
            "S3", "One grade is recorded for each student-course enrolment."
        ),
    ),
    sample_rows=(
        {
            "StudentID": "S001",
            "CourseID": "C101",
            "InstructorID": "I10",
            "InstructorOffice": "B2-14",
            "Grade": "A",
        },
        {
            "StudentID": "S002",
            "CourseID": "C101",
            "InstructorID": "I10",
            "InstructorOffice": "B2-14",
            "Grade": "B+",
        },
        {
            "StudentID": "S001",
            "CourseID": "C205",
            "InstructorID": "I24",
            "InstructorOffice": "N4-03",
            "Grade": "B",
        },
        {
            "StudentID": "S003",
            "CourseID": "C205",
            "InstructorID": "I24",
            "InstructorOffice": "N4-03",
            "Grade": "A-",
        },
    ),
    approved_model_fds=(
        FD(frozenset({"CourseID"}), frozenset({"InstructorID"})),
        FD(frozenset({"InstructorID"}), frozenset({"InstructorOffice"})),
        FD(frozenset({"StudentID", "CourseID"}), frozenset({"Grade"})),
    ),
)


EXERCISES = {COURSE_REGISTRATION_FD.id: COURSE_REGISTRATION_FD}


def get_fd_exercise(exercise_id: str) -> FDExercise | None:
    return EXERCISES.get(exercise_id)


def verify_exercise_for_publication(exercise: FDExercise) -> tuple[FD, ...]:
    """Validate the one approved answer before an exercise is publishable."""
    return validate_approved_answer(
        attributes=frozenset(exercise.attributes),
        approved=exercise.approved_model_fds,
        sample_rows=list(exercise.sample_rows),
    )


for _exercise in EXERCISES.values():
    verify_exercise_for_publication(_exercise)
