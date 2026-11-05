"""Cross-question corpus for the shared BCNF/3NF decomposition engine.

These cases intentionally vary keys, RHS width, implication, preservation policy,
and whether decomposition is needed. They are engine tests, not UI fixtures.
"""

from app.core.normalization.engine import FD, evaluate_recursive_decomposition_process, evaluate_submission
from app.core.normalization.schemas import (
    BCNFDecompositionStepInput,
    BCNFProcessInput,
    FunctionalDependencyInput,
    RelationInput,
    StepRelationInput,
    SubmissionInput,
)


def dependency(lhs: str, rhs: str) -> FD:
    return FD(frozenset(lhs), frozenset(rhs))


def dependency_input(item: FD) -> FunctionalDependencyInput:
    return FunctionalDependencyInput(lhs=sorted(item.lhs), rhs=sorted(item.rhs))


def submission(
    target: str,
    dependencies: list[FD],
    relations: list[RelationInput],
) -> SubmissionInput:
    return SubmissionInput(
        exercise_id="question-corpus",
        target_normal_form=target,
        functional_dependencies=[dependency_input(item) for item in dependencies],
        relations=relations,
    )


def test_bcnf_question_already_in_target_accepts_zero_steps() -> None:
    """Product catalogue: ProductID determines every descriptive attribute."""
    attributes = {"P", "N", "C"}
    dependencies = [dependency("P", "N"), dependency("P", "C")]
    root = StepRelationInput(
        node_id="root", name="PRODUCT", attributes=sorted(attributes), primary_key=["P"]
    )
    process = BCNFProcessInput(workflow="recursive_decomposition", root=root, steps=[])

    process_result = evaluate_recursive_decomposition_process(
        process, attributes, dependencies, [root], "BCNF"
    )
    result = evaluate_submission(
        "already-bcnf",
        submission("BCNF", dependencies, [root]),
        attributes,
        process_evaluation=process_result,
    )

    assert process_result.valid is True
    assert result.meets_requirements is True


def test_3nf_question_prime_attribute_exception_accepts_zero_steps() -> None:
    """Teaching allocation: AB -> C and C -> B is 3NF but not BCNF."""
    attributes = {"A", "B", "C"}
    dependencies = [dependency("AB", "C"), dependency("C", "B")]
    root = StepRelationInput(
        node_id="root", name="ALLOCATION", attributes=sorted(attributes), primary_key=["A", "B"]
    )
    process = BCNFProcessInput(workflow="recursive_decomposition", root=root, steps=[])

    process_result = evaluate_recursive_decomposition_process(
        process, attributes, dependencies, [root], "3NF"
    )
    third_normal_form = evaluate_submission(
        "prime-exception",
        submission("3NF", dependencies, [root]),
        attributes,
        dependency_preservation_required=True,
        process_evaluation=process_result,
    )
    boyce_codd = evaluate_submission(
        "stricter-target", submission("BCNF", dependencies, [root]), attributes
    )

    assert process_result.valid is True
    assert third_normal_form.meets_requirements is True
    assert boyce_codd.relations_satisfy_target is False


def test_bcnf_question_supports_composite_rhs_and_recursive_splits() -> None:
    """Library holdings: A -> BC and D -> E require two BCNF splits."""
    attributes = {"A", "B", "C", "D", "E"}
    dependencies = [dependency("A", "BC"), dependency("D", "E")]
    root = StepRelationInput(node_id="root", name="HOLDING", attributes=sorted(attributes))
    abc = StepRelationInput(node_id="abc", name="ABC", attributes=["A", "B", "C"], primary_key=["A"])
    ade = StepRelationInput(node_id="ade", name="ADE", attributes=["A", "D", "E"], primary_key=["A", "D"])
    de = StepRelationInput(node_id="de", name="DE", attributes=["D", "E"], primary_key=["D"])
    ad = StepRelationInput(node_id="ad", name="AD", attributes=["A", "D"], primary_key=["A", "D"])
    process = BCNFProcessInput(
        workflow="recursive_decomposition",
        root=root,
        steps=[
            BCNFDecompositionStepInput(
                step_id="split-descriptions",
                parent_node_id="root",
                selected_fd=FunctionalDependencyInput(lhs=["A"], rhs=["B", "C"]),
                children=[abc, ade],
            ),
            BCNFDecompositionStepInput(
                step_id="split-location",
                parent_node_id="ade",
                selected_fd=FunctionalDependencyInput(lhs=["D"], rhs=["E"]),
                children=[de, ad],
            ),
        ],
    )
    final_relations = [abc, de, ad]

    process_result = evaluate_recursive_decomposition_process(
        process, attributes, dependencies, final_relations, "BCNF"
    )
    result = evaluate_submission(
        "composite-rhs",
        submission("BCNF", dependencies, final_relations),
        attributes,
        process_evaluation=process_result,
    )

    assert process_result.valid is True
    assert result.lossless_join is True
    assert result.dependency_preservation is True
    assert result.meets_requirements is True


def test_bcnf_question_accepts_an_implied_fd_as_split_evidence() -> None:
    """Shipment chain: A -> C is implied by A -> B and B -> C."""
    attributes = {"A", "B", "C", "D"}
    dependencies = [dependency("A", "B"), dependency("B", "C"), dependency("CD", "A")]
    root = StepRelationInput(node_id="root", name="SHIPMENT", attributes=sorted(attributes))
    ac = StepRelationInput(node_id="ac", name="AC", attributes=["A", "C"], primary_key=["A"])
    abd = StepRelationInput(node_id="abd", name="ABD", attributes=["A", "B", "D"], primary_key=["A", "D"])
    ab = StepRelationInput(node_id="ab", name="AB", attributes=["A", "B"], primary_key=["A"])
    ad = StepRelationInput(node_id="ad", name="AD", attributes=["A", "D"], primary_key=["A", "D"])
    process = BCNFProcessInput(
        workflow="recursive_decomposition",
        root=root,
        steps=[
            BCNFDecompositionStepInput(
                step_id="implied-split",
                parent_node_id="root",
                selected_fd=FunctionalDependencyInput(lhs=["A"], rhs=["C"]),
                children=[ac, abd],
            ),
            BCNFDecompositionStepInput(
                step_id="explicit-split",
                parent_node_id="abd",
                selected_fd=FunctionalDependencyInput(lhs=["A"], rhs=["B"]),
                children=[ab, ad],
            ),
        ],
    )
    final_relations = [ac, ab, ad]

    process_result = evaluate_recursive_decomposition_process(
        process, attributes, dependencies, final_relations, "BCNF"
    )
    result = evaluate_submission(
        "implied-fd",
        submission("BCNF", dependencies, final_relations),
        attributes,
        dependency_preservation_required=False,
        process_evaluation=process_result,
    )

    assert process_result.valid is True
    assert result.lossless_join is True
    assert result.dependency_preservation is False
    assert result.meets_requirements is True


def test_3nf_question_with_mixed_rhs_detects_required_preservation_failure() -> None:
    """Registration: C -> BD has a prime B and non-prime D component."""
    attributes = {"A", "B", "C", "D"}
    dependencies = [dependency("AB", "C"), dependency("C", "BD")]
    root = StepRelationInput(node_id="root", name="REGISTRATION", attributes=sorted(attributes))
    bcd = StepRelationInput(node_id="bcd", name="BCD", attributes=["B", "C", "D"], primary_key=["C"])
    ac = StepRelationInput(node_id="ac", name="AC", attributes=["A", "C"], primary_key=["A", "C"])
    process = BCNFProcessInput(
        workflow="recursive_decomposition",
        root=root,
        steps=[
            BCNFDecompositionStepInput(
                step_id="mixed-rhs",
                parent_node_id="root",
                selected_fd=FunctionalDependencyInput(lhs=["C"], rhs=["B", "D"]),
                children=[bcd, ac],
            )
        ],
    )
    final_relations = [bcd, ac]

    process_result = evaluate_recursive_decomposition_process(
        process, attributes, dependencies, final_relations, "3NF"
    )
    result = evaluate_submission(
        "mixed-rhs",
        submission("3NF", dependencies, final_relations),
        attributes,
        dependency_preservation_required=True,
        process_evaluation=process_result,
    )

    assert process_result.valid is True
    assert result.relations_satisfy_target is True
    assert result.lossless_join is True
    assert result.dependency_preservation is False
    assert result.meets_requirements is False


def test_process_rejects_reusing_a_parent_that_is_no_longer_a_leaf() -> None:
    """A later step cannot decompose a parent that was already replaced."""
    attributes = {"A", "B", "C"}
    dependencies = [dependency("A", "B"), dependency("B", "C")]
    root = StepRelationInput(node_id="root", name="R", attributes=sorted(attributes))
    ab = StepRelationInput(node_id="ab", name="AB", attributes=["A", "B"], primary_key=["A"])
    ac = StepRelationInput(node_id="ac", name="AC", attributes=["A", "C"], primary_key=["A"])
    bc = StepRelationInput(node_id="bc", name="BC", attributes=["B", "C"], primary_key=["B"])
    process = BCNFProcessInput(
        workflow="recursive_decomposition",
        root=root,
        steps=[
            BCNFDecompositionStepInput(
                step_id="first",
                parent_node_id="root",
                selected_fd=FunctionalDependencyInput(lhs=["B"], rhs=["C"]),
                children=[bc, ab],
            ),
            BCNFDecompositionStepInput(
                step_id="reuse-root",
                parent_node_id="root",
                selected_fd=FunctionalDependencyInput(lhs=["A"], rhs=["B"]),
                children=[ab, ac],
            ),
        ],
    )

    result = evaluate_recursive_decomposition_process(
        process, attributes, dependencies, [bc, ab], "BCNF"
    )

    assert result.valid is False
    assert "not an active leaf" in result.errors[0]


def test_process_rejects_trivial_fd_and_duplicate_child_identifiers() -> None:
    """Malformed construction evidence is rejected independently of final cards."""
    attributes = {"A", "B", "C"}
    dependencies = [dependency("A", "B")]
    root = StepRelationInput(node_id="root", name="R", attributes=sorted(attributes))
    first = StepRelationInput(node_id="duplicate", name="A", attributes=["A"], primary_key=["A"])
    second = StepRelationInput(node_id="duplicate", name="ABC", attributes=["A", "B", "C"], primary_key=["A", "C"])
    process = BCNFProcessInput(
        workflow="recursive_decomposition",
        root=root,
        steps=[
            BCNFDecompositionStepInput(
                step_id="bad-step",
                parent_node_id="root",
                selected_fd=FunctionalDependencyInput(lhs=["A"], rhs=["A"]),
                children=[first, second],
            )
        ],
    )

    result = evaluate_recursive_decomposition_process(
        process, attributes, dependencies, [root], "BCNF"
    )

    assert result.valid is False
    assert any("trivial FD" in error for error in result.errors)
    assert any("different node identifiers" in error for error in result.errors)
