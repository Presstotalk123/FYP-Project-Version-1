from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .schemas import (
    BCNFProcessInput,
    FunctionalDependencyInput,
    NormalizationProcessEvaluation,
    ProcessStepEvaluation,
    RelationEvaluation,
    RelationInput,
    SubmissionEvaluation,
    SubmissionInput,
    ThreeNFProcessInput,
)


NORMALIZATION_ENGINE_VERSION = "phase2-2.1"


@dataclass(frozen=True)
class FD:
    lhs: frozenset[str]
    rhs: frozenset[str]


def powerset(attributes: set[str]):
    ordered = sorted(attributes)
    for size in range(len(ordered) + 1):
        for items in combinations(ordered, size):
            yield frozenset(items)


def closure(seed: frozenset[str], dependencies: list[FD]) -> frozenset[str]:
    result = set(seed)
    changed = True
    while changed:
        changed = False
        for dependency in dependencies:
            if dependency.lhs <= result and not dependency.rhs <= result:
                result.update(dependency.rhs)
                changed = True
    return frozenset(result)


@dataclass(frozen=True)
class ClosureStep:
    dependency: FD
    introduced: frozenset[str]
    closure: frozenset[str]


def closure_with_trace(
    seed: frozenset[str], dependencies: list[FD]
) -> tuple[frozenset[str], list[ClosureStep]]:
    """Return a deterministic closure and the FD responsible for every expansion."""
    result = set(seed)
    steps: list[ClosureStep] = []
    ordered = sorted(
        split_rhs(dependencies),
        key=lambda fd: (len(fd.lhs), tuple(sorted(fd.lhs)), tuple(sorted(fd.rhs))),
    )
    changed = True
    while changed:
        changed = False
        for dependency in ordered:
            introduced = dependency.rhs - result
            if dependency.lhs <= result and introduced:
                result.update(introduced)
                steps.append(
                    ClosureStep(
                        dependency=dependency,
                        introduced=frozenset(introduced),
                        closure=frozenset(result),
                    )
                )
                changed = True
    return frozenset(result), steps


def split_rhs(dependencies: list[FD]) -> list[FD]:
    return sorted(
        {
            FD(dependency.lhs, frozenset({attribute}))
            for dependency in dependencies
            for attribute in dependency.rhs
        },
        key=lambda fd: (len(fd.lhs), tuple(sorted(fd.lhs)), tuple(sorted(fd.rhs))),
    )


def minimal_cover(dependencies: list[FD]) -> list[FD]:
    """Derive a stable singleton-RHS minimal cover."""
    cover = split_rhs(dependencies)

    for index, dependency in enumerate(list(cover)):
        determinant = set(dependency.lhs)
        for attribute in sorted(dependency.lhs):
            candidate = frozenset(determinant - {attribute})
            if dependency.rhs <= closure(candidate, cover):
                determinant.remove(attribute)
                replacement = FD(frozenset(determinant), dependency.rhs)
                current_index = cover.index(dependency) if dependency in cover else index
                cover[current_index] = replacement
                dependency = replacement

    index = 0
    while index < len(cover):
        dependency = cover[index]
        remainder = cover[:index] + cover[index + 1 :]
        if dependency.rhs <= closure(dependency.lhs, remainder):
            cover.pop(index)
        else:
            index += 1

    return sorted(
        set(cover),
        key=lambda fd: (len(fd.lhs), tuple(sorted(fd.lhs)), tuple(sorted(fd.rhs))),
    )


def projected_dependencies(relation: set[str], dependencies: list[FD]) -> list[FD]:
    projected: set[FD] = set()
    for lhs in powerset(relation):
        implied = (closure(lhs, dependencies) & relation) - lhs
        for attribute in implied:
            projected.add(FD(lhs=lhs, rhs=frozenset({attribute})))
    return sorted(projected, key=lambda fd: (len(fd.lhs), sorted(fd.lhs), sorted(fd.rhs)))


def candidate_keys(relation: set[str], dependencies: list[FD]) -> list[frozenset[str]]:
    keys: list[frozenset[str]] = []
    for candidate in powerset(relation):
        if any(key <= candidate for key in keys):
            continue
        if (closure(candidate, dependencies) & relation) == relation:
            keys.append(candidate)
    return keys


def relation_evaluation(
    relation: RelationInput,
    dependencies: list[FD],
    target: str,
) -> RelationEvaluation:
    attributes = set(relation.attributes)
    projected = projected_dependencies(attributes, dependencies)
    keys = candidate_keys(attributes, projected)
    prime = set().union(*keys) if keys else set()
    violations: list[str] = []

    for dependency in projected:
        if not dependency.rhs - dependency.lhs:
            continue
        determinant_is_superkey = closure(dependency.lhs, projected) >= attributes
        dependent_is_prime = dependency.rhs <= prime
        violates = (
            not determinant_is_superkey
            if target == "BCNF"
            else not determinant_is_superkey and not dependent_is_prime
        )
        if violates:
            left = ", ".join(sorted(dependency.lhs)) or "∅"
            right = ", ".join(sorted(dependency.rhs))
            violations.append(f"{left} → {right}")

    return RelationEvaluation(
        name=relation.name,
        candidate_keys=[sorted(key) for key in keys],
        prime_attributes=sorted(prime),
        satisfies_target=not violations,
        violations=violations,
        proposed_primary_key=sorted(relation.primary_key),
        proposed_key_is_candidate=frozenset(relation.primary_key) in keys,
    )


def chase_lossless(
    original_attributes: set[str],
    relations: list[RelationInput],
    dependencies: list[FD],
) -> bool:
    attributes = sorted(original_attributes)
    index = {attribute: column for column, attribute in enumerate(attributes)}
    table: list[list[str]] = []

    for row_number, relation in enumerate(relations):
        relation_attributes = set(relation.attributes)
        table.append(
            [
                f"a:{attribute}" if attribute in relation_attributes else f"b:{row_number}:{attribute}"
                for attribute in attributes
            ]
        )

    changed = True
    while changed:
        changed = False
        for dependency in dependencies:
            if not dependency.lhs <= original_attributes:
                continue
            for first in range(len(table)):
                for second in range(first + 1, len(table)):
                    if all(
                        table[first][index[attribute]] == table[second][index[attribute]]
                        for attribute in dependency.lhs
                    ):
                        for attribute in dependency.rhs & original_attributes:
                            column = index[attribute]
                            left_symbol = table[first][column]
                            right_symbol = table[second][column]
                            if left_symbol == right_symbol:
                                continue
                            preferred = (
                                left_symbol
                                if left_symbol.startswith("a:")
                                else right_symbol
                                if right_symbol.startswith("a:")
                                else min(left_symbol, right_symbol)
                            )
                            replaced = right_symbol if preferred == left_symbol else left_symbol
                            for row in table:
                                for cell in range(len(row)):
                                    if row[cell] == replaced:
                                        row[cell] = preferred
                            changed = True

    expected = [f"a:{attribute}" for attribute in attributes]
    return any(row == expected for row in table)


def dependency_preservation(
    relations: list[RelationInput], dependencies: list[FD]
) -> tuple[bool, list[str]]:
    union_projection: set[FD] = set()
    for relation in relations:
        union_projection.update(projected_dependencies(set(relation.attributes), dependencies))
    projected = list(union_projection)
    missing: list[str] = []
    for dependency in dependencies:
        if not dependency.rhs <= closure(dependency.lhs, projected):
            left = ", ".join(sorted(dependency.lhs))
            right = ", ".join(sorted(dependency.rhs))
            missing.append(f"{left} → {right}")
    return not missing, missing


def _input_fd(item: FunctionalDependencyInput) -> FD:
    return FD(frozenset(item.lhs), frozenset(item.rhs))


def _fd_text(dependency: FD) -> str:
    left = ", ".join(sorted(dependency.lhs)) or "∅"
    right = ", ".join(sorted(dependency.rhs))
    return f"{left} → {right}"


def _implies(source: list[FD], target: list[FD]) -> bool:
    return all(item.rhs <= closure(item.lhs, source) for item in target)


def evaluate_recursive_decomposition_process(
    process: BCNFProcessInput,
    original_attributes: set[str],
    dependencies: list[FD],
    final_relations: list[RelationInput],
    target_normal_form: str,
) -> NormalizationProcessEvaluation:
    """Validate one recursive decomposition against the assigned normal form."""
    errors: list[str] = []
    step_results: list[ProcessStepEvaluation] = []
    root_attributes = set(process.root.attributes)
    if root_attributes != original_attributes:
        errors.append("The root relation must contain exactly the original attributes.")

    active_leaves: dict[str, set[str]] = {process.root.node_id: root_attributes}
    used_node_ids = {process.root.node_id}

    for position, step in enumerate(process.steps, start=1):
        step_errors: list[str] = []
        parent = active_leaves.get(step.parent_node_id)
        selected = _input_fd(step.selected_fd)

        if parent is None:
            step_errors.append("The selected parent is not an active leaf relation.")
        else:
            if not selected.lhs | selected.rhs <= parent:
                step_errors.append("The selected FD contains attributes outside its parent relation.")
            else:
                projected = projected_dependencies(parent, dependencies)
                if not selected.rhs <= closure(selected.lhs, projected):
                    step_errors.append("The selected FD is not implied in the parent relation.")
                if not selected.rhs - selected.lhs:
                    step_errors.append("A trivial FD cannot justify a decomposition.")
                determinant_is_superkey = closure(selected.lhs, projected) >= parent
                keys = candidate_keys(parent, projected)
                prime_attributes = set().union(*keys) if keys else set()
                dependent_is_prime = selected.rhs <= prime_attributes
                violates_target = (
                    not determinant_is_superkey
                    if target_normal_form == "BCNF"
                    else not determinant_is_superkey and not dependent_is_prime
                )
                if not violates_target:
                    if target_normal_form == "BCNF":
                        step_errors.append(
                            "The determinant is a superkey, so this FD is not a BCNF violation."
                        )
                    else:
                        step_errors.append(
                            "This FD is not a 3NF violation: its determinant is a superkey or its dependent is prime."
                        )

            child_ids = [child.node_id for child in step.children]
            if len(set(child_ids)) != 2:
                step_errors.append("The two child relations must have different node identifiers.")
            if any(node_id in used_node_ids for node_id in child_ids):
                step_errors.append("Every relation node must have a unique identifier.")

            expected_children = {
                frozenset(selected.lhs | selected.rhs),
                frozenset(parent - (selected.rhs - selected.lhs)),
            }
            actual_children = {
                frozenset(child.attributes) for child in step.children
            }
            if len(actual_children) != 2 or actual_children != expected_children:
                step_errors.append(
                    "The two child attribute sets do not match the lossless decomposition rule."
                )

        valid = not step_errors
        if valid and parent is not None:
            del active_leaves[step.parent_node_id]
            for child in step.children:
                active_leaves[child.node_id] = set(child.attributes)
                used_node_ids.add(child.node_id)

        feedback = (
            f"Step {position} is a valid split using {_fd_text(selected)}."
            if valid
            else " ".join(step_errors)
        )
        step_results.append(
            ProcessStepEvaluation(step=step.step_id, valid=valid, feedback=feedback)
        )
        errors.extend(f"Step {position}: {message}" for message in step_errors)

    leaf_signatures = sorted(tuple(sorted(attributes)) for attributes in active_leaves.values())
    final_signatures = sorted(tuple(sorted(relation.attributes)) for relation in final_relations)
    if leaf_signatures != final_signatures:
        errors.append("The submitted final relations must be exactly the active leaves of the decomposition.")

    return NormalizationProcessEvaluation(
        workflow="recursive_decomposition",
        valid=not errors,
        step_results=step_results,
        errors=errors,
    )


def evaluate_bcnf_process(
    process: BCNFProcessInput,
    original_attributes: set[str],
    dependencies: list[FD],
    final_relations: list[RelationInput],
) -> NormalizationProcessEvaluation:
    """Backward-compatible BCNF wrapper for existing callers and tests."""
    return evaluate_recursive_decomposition_process(
        process,
        original_attributes,
        dependencies,
        final_relations,
        "BCNF",
    )


def evaluate_3nf_process(
    process: ThreeNFProcessInput,
    original_attributes: set[str],
    dependencies: list[FD],
    final_relations: list[RelationInput],
) -> NormalizationProcessEvaluation:
    """Validate the student's minimal-cover and 3NF synthesis construction."""
    errors: list[str] = []
    step_results: list[ProcessStepEvaluation] = []
    proposed = [_input_fd(item) for item in process.proposed_minimal_cover]
    proposed_set = set(proposed)

    cover_errors: list[str] = []
    if any((item.lhs | item.rhs) - original_attributes for item in proposed):
        cover_errors.append("The proposed cover contains attributes outside the exercise relation.")
    if len(proposed) != len(proposed_set):
        cover_errors.append("The proposed cover contains duplicate dependencies.")
    if any(len(item.rhs) != 1 for item in proposed):
        cover_errors.append("Every dependency in a minimal cover must have a single RHS attribute.")
    if not _implies(proposed, dependencies) or not _implies(dependencies, proposed):
        cover_errors.append("The proposed cover is not logically equivalent to the original FD set.")

    for item in proposed:
        for attribute in item.lhs:
            if item.rhs <= closure(item.lhs - {attribute}, proposed):
                cover_errors.append(
                    f"{attribute} is extraneous in the determinant of {_fd_text(item)}."
                )
        remainder = list(proposed)
        remainder.remove(item)
        if item.rhs <= closure(item.lhs, remainder):
            cover_errors.append(f"{_fd_text(item)} is redundant in the proposed cover.")

    cover_valid = not cover_errors
    step_results.append(
        ProcessStepEvaluation(
            step="minimal-cover",
            valid=cover_valid,
            feedback=(
                "The proposed FD set is a valid minimal cover."
                if cover_valid
                else " ".join(cover_errors)
            ),
        )
    )
    errors.extend(cover_errors)

    synthesis_errors: list[str] = []
    relations_by_name = {relation.name.casefold(): relation for relation in final_relations}
    supported: set[FD] = set()
    seen_names: set[str] = set()
    for justification in process.synthesis_relations:
        name = justification.relation_name.casefold()
        if name in seen_names:
            synthesis_errors.append(
                f"Relation {justification.relation_name} has more than one justification entry."
            )
            continue
        seen_names.add(name)
        relation = relations_by_name.get(name)
        if relation is None:
            synthesis_errors.append(
                f"Justification refers to unknown relation {justification.relation_name}."
            )
            continue
        attributes = set(relation.attributes)
        for raw_fd in justification.supporting_fds:
            supporting = _input_fd(raw_fd)
            if supporting not in proposed_set:
                synthesis_errors.append(
                    f"{_fd_text(supporting)} is not in the proposed minimal cover."
                )
            elif supporting.lhs | supporting.rhs <= attributes:
                supported.add(supporting)
            else:
                synthesis_errors.append(
                    f"Relation {relation.name} does not contain all attributes of {_fd_text(supporting)}."
                )

    unjustified_relations = set(relations_by_name) - seen_names
    if unjustified_relations:
        synthesis_errors.append("Every synthesized relation requires a justification.")
    unsupported = proposed_set - supported
    if unsupported:
        synthesis_errors.append(
            "Every dependency in the proposed cover must support at least one synthesized relation."
        )

    original_keys = candidate_keys(original_attributes, dependencies)
    if not any(
        key <= set(relation.attributes)
        for key in original_keys
        for relation in final_relations
    ):
        synthesis_errors.append("At least one synthesized relation must contain an original candidate key.")

    relation_sets = [set(relation.attributes) for relation in final_relations]
    if any(
        first < second
        for index, first in enumerate(relation_sets)
        for other_index, second in enumerate(relation_sets)
        if index != other_index
    ):
        synthesis_errors.append("Remove any synthesized relation contained in another relation.")

    synthesis_valid = not synthesis_errors
    step_results.append(
        ProcessStepEvaluation(
            step="synthesis",
            valid=synthesis_valid,
            feedback=(
                "The relation construction is justified by the proposed minimal cover."
                if synthesis_valid
                else " ".join(synthesis_errors)
            ),
        )
    )
    errors.extend(synthesis_errors)

    return NormalizationProcessEvaluation(
        workflow="synthesis",
        valid=not errors,
        step_results=step_results,
        errors=errors,
    )


def evaluate_submission(
    submission_id: str,
    submission: SubmissionInput,
    original_attributes: set[str],
    dependency_preservation_required: bool = False,
    process_evaluation: NormalizationProcessEvaluation | None = None,
) -> SubmissionEvaluation:
    dependencies = [
        FD(frozenset(item.lhs), frozenset(item.rhs))
        for item in submission.functional_dependencies
    ]
    covered = set().union(*(set(relation.attributes) for relation in submission.relations))
    missing_attributes = sorted(original_attributes - covered)
    relation_results = [
        relation_evaluation(relation, dependencies, submission.target_normal_form)
        for relation in submission.relations
    ]
    preserved, unpreserved = dependency_preservation(submission.relations, dependencies)
    proposed_keys_correct = all(
        result.proposed_key_is_candidate for result in relation_results
    )
    attribute_coverage = not missing_attributes
    lossless_join = chase_lossless(
        original_attributes, submission.relations, dependencies
    )
    relations_satisfy_target = all(
        result.satisfies_target for result in relation_results
    )
    meets_requirements = (
        attribute_coverage
        and lossless_join
        and relations_satisfy_target
        and proposed_keys_correct
        and (preserved or not dependency_preservation_required)
        and (process_evaluation is None or process_evaluation.valid)
    )

    return SubmissionEvaluation(
        submission_id=submission_id,
        engine_version=NORMALIZATION_ENGINE_VERSION,
        target_normal_form=submission.target_normal_form,
        attribute_coverage=attribute_coverage,
        missing_attributes=missing_attributes,
        lossless_join=lossless_join,
        dependency_preservation=preserved,
        unpreserved_dependencies=unpreserved,
        relations_satisfy_target=relations_satisfy_target,
        relation_results=relation_results,
        dependency_preservation_required=dependency_preservation_required,
        proposed_keys_correct=proposed_keys_correct,
        meets_requirements=meets_requirements,
        process_evaluation=process_evaluation,
        note=(
            "Results are deterministic checks against the exercise's authoritative "
            "relation and functional dependencies."
        ),
    )
