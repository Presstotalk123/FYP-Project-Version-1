"""Pure deterministic logic for the Phase 1 functional-dependency workspace."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Mapping


@dataclass(frozen=True)
class FD:
    lhs: frozenset[str]
    rhs: frozenset[str]


@dataclass(frozen=True)
class SampleContradiction:
    fd: FD
    first_row: int
    second_row: int


@dataclass(frozen=True)
class PartialOverlap:
    reference_coverage: float
    submission_soundness: float
    reference_matched: int
    reference_total: int
    submission_matched: int
    submission_total: int


class FDValidationError(ValueError):
    """Raised when an FD set cannot be used for deterministic evaluation."""


def fd_sort_key(fd: FD) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    return len(fd.lhs), tuple(sorted(fd.lhs)), tuple(sorted(fd.rhs))


def closure(seed: frozenset[str], dependencies: Iterable[FD]) -> frozenset[str]:
    result = set(seed)
    dependency_list = tuple(dependencies)
    changed = True
    while changed:
        changed = False
        for dependency in dependency_list:
            if dependency.lhs <= result and not dependency.rhs <= result:
                result.update(dependency.rhs)
                changed = True
    return frozenset(result)


def canonicalize(dependencies: Iterable[FD]) -> tuple[FD, ...]:
    """Split RHS values, remove duplicates, and return a stable ordering."""
    atomic: set[FD] = set()
    for dependency in dependencies:
        if not dependency.lhs:
            raise FDValidationError("Every functional dependency needs a determinant.")
        if not dependency.rhs:
            raise FDValidationError("Every functional dependency needs a dependent side.")
        for attribute in dependency.rhs:
            atomic.add(FD(dependency.lhs, frozenset({attribute})))
    return tuple(sorted(atomic, key=fd_sort_key))


def validate_domain(dependencies: Iterable[FD], attributes: frozenset[str]) -> None:
    for dependency in dependencies:
        unknown = (dependency.lhs | dependency.rhs) - attributes
        if unknown:
            raise FDValidationError(
                f"Unknown relation attributes: {', '.join(sorted(unknown))}."
            )


def non_trivial(dependencies: Iterable[FD]) -> tuple[FD, ...]:
    return tuple(fd for fd in canonicalize(dependencies) if not fd.rhs <= fd.lhs)


def implies(source: Iterable[FD], target: Iterable[FD]) -> bool:
    source_canonical = canonicalize(source)
    return all(
        dependency.rhs <= closure(dependency.lhs, source_canonical)
        for dependency in canonicalize(target)
    )


def logically_equivalent(first: Iterable[FD], second: Iterable[FD]) -> bool:
    first_canonical = canonicalize(first)
    second_canonical = canonicalize(second)
    return implies(first_canonical, second_canonical) and implies(
        second_canonical, first_canonical
    )


def minimal_cover(dependencies: Iterable[FD]) -> tuple[FD, ...]:
    """Return one deterministic minimal cover for a meaningful FD set."""
    cover = list(non_trivial(dependencies))
    changed = True
    while changed:
        changed = False
        for index, dependency in enumerate(tuple(cover)):
            for attribute in sorted(dependency.lhs):
                reduced_lhs = dependency.lhs - {attribute}
                if dependency.rhs <= closure(reduced_lhs, cover):
                    cover[index] = FD(reduced_lhs, dependency.rhs)
                    cover = list(canonicalize(cover))
                    changed = True
                    break
            if changed:
                break

    for dependency in tuple(sorted(cover, key=fd_sort_key)):
        if dependency not in cover:
            continue
        others = list(cover)
        others.remove(dependency)
        if dependency.rhs <= closure(dependency.lhs, others):
            cover.remove(dependency)

    return tuple(sorted(set(cover), key=fd_sort_key))


def partial_overlap(
    submitted: Iterable[FD], approved: Iterable[FD]
) -> PartialOverlap:
    submitted_canonical = canonicalize(submitted)
    approved_canonical = canonicalize(approved)
    student_basis = non_trivial(submitted_canonical)
    reference_basis = minimal_cover(approved_canonical)

    if not reference_basis:
        raise FDValidationError(
            "The approved model answer must contain a non-trivial dependency."
        )
    if not student_basis:
        return PartialOverlap(0.0, 0.0, 0, len(reference_basis), 0, 0)

    reference_matched = sum(
        dependency.rhs <= closure(dependency.lhs, submitted_canonical)
        for dependency in reference_basis
    )
    submission_matched = sum(
        dependency.rhs <= closure(dependency.lhs, approved_canonical)
        for dependency in student_basis
    )
    return PartialOverlap(
        reference_coverage=reference_matched / len(reference_basis),
        submission_soundness=submission_matched / len(student_basis),
        reference_matched=reference_matched,
        reference_total=len(reference_basis),
        submission_matched=submission_matched,
        submission_total=len(student_basis),
    )


def sample_contradictions(
    dependencies: Iterable[FD], sample_rows: list[Mapping[str, object]]
) -> tuple[SampleContradiction, ...]:
    contradictions: list[SampleContradiction] = []
    for dependency in non_trivial(dependencies):
        lhs = tuple(sorted(dependency.lhs))
        rhs = tuple(sorted(dependency.rhs))
        for first_index, second_index in combinations(range(len(sample_rows)), 2):
            first = sample_rows[first_index]
            second = sample_rows[second_index]
            if all(first.get(attribute) == second.get(attribute) for attribute in lhs) and any(
                first.get(attribute) != second.get(attribute) for attribute in rhs
            ):
                contradictions.append(
                    SampleContradiction(dependency, first_index + 1, second_index + 1)
                )
                break
    return tuple(contradictions)


def validate_sample_shape(
    attributes: frozenset[str], sample_rows: list[Mapping[str, object]]
) -> None:
    for index, row in enumerate(sample_rows, start=1):
        row_attributes = frozenset(row)
        if row_attributes != attributes:
            missing = sorted(attributes - row_attributes)
            extra = sorted(row_attributes - attributes)
            details: list[str] = []
            if missing:
                details.append(f"missing {', '.join(missing)}")
            if extra:
                details.append(f"unexpected {', '.join(extra)}")
            raise FDValidationError(f"Sample row {index} has {'; '.join(details)}.")
        if any(value is None for value in row.values()):
            raise FDValidationError(f"Sample row {index} contains a null value.")


def validate_approved_answer(
    *,
    attributes: frozenset[str],
    approved: Iterable[FD],
    sample_rows: list[Mapping[str, object]],
) -> tuple[FD, ...]:
    approved_canonical = canonicalize(approved)
    validate_domain(approved_canonical, attributes)
    validate_sample_shape(attributes, sample_rows)
    cover = minimal_cover(approved_canonical)
    if not cover:
        raise FDValidationError(
            "The approved model answer must contain a non-trivial dependency."
        )
    contradictions = sample_contradictions(approved_canonical, sample_rows)
    if contradictions:
        first = contradictions[0]
        raise FDValidationError(
            "Approved dependency "
            f"{format_fd(first.fd)} is contradicted by sample rows "
            f"{first.first_row} and {first.second_row}."
        )
    return cover


def format_fd(dependency: FD) -> str:
    return f"{', '.join(sorted(dependency.lhs))} -> {', '.join(sorted(dependency.rhs))}"
