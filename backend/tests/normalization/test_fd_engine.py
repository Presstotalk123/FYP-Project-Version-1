import pytest

from app.core.normalization.fd_engine import (
    FD,
    FDValidationError,
    canonicalize,
    logically_equivalent,
    minimal_cover,
    partial_overlap,
    sample_contradictions,
    validate_approved_answer,
    validate_domain,
    validate_sample_shape,
)
from app.core.normalization.fd_exercises import COURSE_REGISTRATION_FD, verify_exercise_for_publication


def fd(lhs: str, rhs: str) -> FD:
    return FD(frozenset(lhs), frozenset(rhs))


def test_canonicalization_splits_rhs_removes_duplicates_and_is_stable() -> None:
    dependencies = [fd("A", "CB"), fd("A", "B"), fd("BA", "C")]
    assert canonicalize(dependencies) == (
        fd("A", "B"),
        fd("A", "C"),
        fd("AB", "C"),
    )
    assert canonicalize(canonicalize(dependencies)) == canonicalize(dependencies)


def test_domain_validation_rejects_unknown_attributes() -> None:
    with pytest.raises(FDValidationError, match="Unknown relation attributes: C"):
        validate_domain([fd("A", "C")], frozenset({"A", "B"}))


def test_implication_equivalence_and_stable_minimal_cover() -> None:
    first = [fd("A", "BC"), fd("B", "C")]
    equivalent = [fd("A", "B"), fd("B", "C")]
    assert logically_equivalent(first, equivalent)
    assert minimal_cover(first) == (fd("A", "B"), fd("B", "C"))
    assert minimal_cover(reversed(first)) == minimal_cover(first)


def test_partial_overlap_excludes_duplicates_trivial_fds_and_redundancy() -> None:
    approved = [fd("A", "B"), fd("B", "C"), fd("A", "C")]
    submitted = [fd("A", "B"), fd("A", "B"), fd("A", "A")]
    overlap = partial_overlap(submitted, approved)
    assert overlap.reference_total == 2
    assert overlap.reference_matched == 1
    assert overlap.reference_coverage == 0.5
    assert overlap.submission_total == 1
    assert overlap.submission_matched == 1
    assert overlap.submission_soundness == 1.0


def test_trivial_only_submission_has_defined_zero_scores() -> None:
    overlap = partial_overlap([fd("A", "A")], [fd("A", "B")])
    assert overlap.reference_coverage == 0.0
    assert overlap.submission_soundness == 0.0
    assert overlap.submission_total == 0


def test_empty_reference_basis_is_invalid() -> None:
    with pytest.raises(FDValidationError, match="non-trivial"):
        partial_overlap([fd("A", "B")], [fd("A", "A")])


def test_sample_rows_disprove_but_do_not_prove_dependencies() -> None:
    rows = [
        {"StudentID": "S1", "CourseID": "C1", "Grade": "A"},
        {"StudentID": "S2", "CourseID": "C1", "Grade": "B"},
    ]
    contradiction = sample_contradictions(
        [FD(frozenset({"CourseID"}), frozenset({"Grade"}))], rows
    )
    assert len(contradiction) == 1
    assert (contradiction[0].first_row, contradiction[0].second_row) == (1, 2)
    assert sample_contradictions(
        [FD(frozenset({"StudentID"}), frozenset({"Grade"}))], rows
    ) == ()


def test_approved_answer_publication_validation() -> None:
    cover = verify_exercise_for_publication(COURSE_REGISTRATION_FD)
    assert cover

    rows = [{"A": "1", "B": "x"}, {"A": "1", "B": "y"}]
    with pytest.raises(FDValidationError, match="contradicted"):
        validate_approved_answer(
            attributes=frozenset({"A", "B"}),
            approved=[fd("A", "B")],
            sample_rows=rows,
        )


def test_sample_shape_rejects_missing_extra_and_null_values() -> None:
    with pytest.raises(FDValidationError, match="missing B"):
        validate_sample_shape(frozenset({"A", "B"}), [{"A": "1"}])
    with pytest.raises(FDValidationError, match="null"):
        validate_sample_shape(frozenset({"A", "B"}), [{"A": "1", "B": None}])
