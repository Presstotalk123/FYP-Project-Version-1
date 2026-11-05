from app.core.normalization.engine import (
    FD,
    candidate_keys,
    closure,
    closure_with_trace,
    evaluate_3nf_process,
    evaluate_bcnf_process,
    evaluate_recursive_decomposition_process,
    evaluate_submission,
    minimal_cover,
    relation_evaluation,
)
from app.core.normalization.schemas import (
    BCNFDecompositionStepInput,
    BCNFProcessInput,
    FunctionalDependencyInput,
    RelationInput,
    StepRelationInput,
    SubmissionInput,
    SynthesisRelationJustificationInput,
    ThreeNFProcessInput,
)


ATTRIBUTES = {"StudentID", "CourseID", "InstructorID", "InstructorOffice", "Grade"}
FDS = [
    FD(frozenset({"StudentID", "CourseID"}), frozenset({"Grade"})),
    FD(frozenset({"CourseID"}), frozenset({"InstructorID"})),
    FD(frozenset({"InstructorID"}), frozenset({"InstructorOffice"})),
]


def test_closure_and_candidate_key() -> None:
    result = closure(frozenset({"StudentID", "CourseID"}), FDS)
    assert result == ATTRIBUTES
    assert candidate_keys(ATTRIBUTES, FDS) == [frozenset({"CourseID", "StudentID"})]


def test_known_bcnf_decomposition() -> None:
    payload = SubmissionInput(
        functional_dependencies=[
            FunctionalDependencyInput(lhs=sorted(fd.lhs), rhs=sorted(fd.rhs)) for fd in FDS
        ],
        relations=[
            RelationInput(
                name="ENROLLMENT",
                attributes=["StudentID", "CourseID", "Grade"],
                primary_key=["StudentID", "CourseID"],
            ),
            RelationInput(
                name="COURSE_TEACHER",
                attributes=["CourseID", "InstructorID"],
                primary_key=["CourseID"],
            ),
            RelationInput(
                name="INSTRUCTOR_OFFICE",
                attributes=["InstructorID", "InstructorOffice"],
                primary_key=["InstructorID"],
            ),
        ],
    )
    result = evaluate_submission("test", payload, ATTRIBUTES)
    assert result.attribute_coverage is True
    assert result.lossless_join is True
    assert result.dependency_preservation is True
    assert result.relations_satisfy_target is True
    assert result.proposed_keys_correct is True
    assert result.meets_requirements is True


def test_closure_trace_identifies_each_introducing_dependency() -> None:
    result, steps = closure_with_trace(
        frozenset({"StudentID", "CourseID"}), FDS
    )
    assert result == ATTRIBUTES
    assert [step.introduced for step in steps] == [
        frozenset({"InstructorID"}),
        frozenset({"InstructorOffice"}),
        frozenset({"Grade"}),
    ]
    assert steps[-1].closure == ATTRIBUTES


def test_stable_minimal_cover_removes_redundant_dependency() -> None:
    dependencies = FDS + [
        FD(
            frozenset({"StudentID", "CourseID"}),
            frozenset({"InstructorOffice"}),
        )
    ]
    assert set(minimal_cover(dependencies)) == set(FDS)


def test_3nf_relation_can_validly_fail_bcnf() -> None:
    dependencies = [
        FD(frozenset({"A", "B"}), frozenset({"C"})),
        FD(frozenset({"C"}), frozenset({"B"})),
    ]
    relation = RelationInput(
        name="R1",
        attributes=["A", "B", "C"],
        primary_key=["A", "B"],
    )
    third_normal_form = relation_evaluation(relation, dependencies, "3NF")
    boyce_codd = relation_evaluation(relation, dependencies, "BCNF")

    assert third_normal_form.satisfies_target is True
    assert boyce_codd.satisfies_target is False
    assert "C → B" in boyce_codd.violations


def test_dependency_preservation_policy_changes_overall_result() -> None:
    dependencies = [
        FunctionalDependencyInput(lhs=["A", "B"], rhs=["C"]),
        FunctionalDependencyInput(lhs=["C"], rhs=["B"]),
    ]
    payload = SubmissionInput(
        exercise_id="policy-test",
        target_normal_form="BCNF",
        functional_dependencies=dependencies,
        relations=[
            RelationInput(name="R1", attributes=["B", "C"], primary_key=["C"]),
            RelationInput(name="R2", attributes=["A", "C"], primary_key=["A", "C"]),
        ],
    )
    advisory = evaluate_submission(
        "advisory", payload, {"A", "B", "C"}, dependency_preservation_required=False
    )
    required = evaluate_submission(
        "required", payload, {"A", "B", "C"}, dependency_preservation_required=True
    )

    assert advisory.dependency_preservation is False
    assert advisory.meets_requirements is True
    assert required.meets_requirements is False


def test_bcnf_process_validates_each_recursive_split() -> None:
    office = StepRelationInput(node_id="office", name="OFFICE", attributes=["InstructorID", "InstructorOffice"], primary_key=["InstructorID"])
    remaining = StepRelationInput(node_id="remaining", name="REMAINING", attributes=["StudentID", "CourseID", "InstructorID", "Grade"], primary_key=["StudentID", "CourseID"])
    teacher = StepRelationInput(node_id="teacher", name="TEACHER", attributes=["CourseID", "InstructorID"], primary_key=["CourseID"])
    enrolment = StepRelationInput(node_id="enrolment", name="ENROLMENT", attributes=["StudentID", "CourseID", "Grade"], primary_key=["StudentID", "CourseID"])
    process = BCNFProcessInput(
        workflow="recursive_decomposition",
        root=StepRelationInput(node_id="root", name="R", attributes=sorted(ATTRIBUTES)),
        steps=[
            BCNFDecompositionStepInput(step_id="one", parent_node_id="root", selected_fd=FunctionalDependencyInput(lhs=["InstructorID"], rhs=["InstructorOffice"]), children=[office, remaining]),
            BCNFDecompositionStepInput(step_id="two", parent_node_id="remaining", selected_fd=FunctionalDependencyInput(lhs=["CourseID"], rhs=["InstructorID"]), children=[teacher, enrolment]),
        ],
    )

    result = evaluate_bcnf_process(process, ATTRIBUTES, FDS, [office, teacher, enrolment])

    assert result.valid is True
    assert all(step.valid for step in result.step_results)


def test_3nf_recursive_process_uses_prime_attribute_exception() -> None:
    dependencies = [
        FD(frozenset({"A", "B"}), frozenset({"C"})),
        FD(frozenset({"C"}), frozenset({"B"})),
        FD(frozenset({"C"}), frozenset({"D"})),
    ]
    root = StepRelationInput(node_id="root", name="R", attributes=["A", "B", "C", "D"])
    cd = StepRelationInput(node_id="cd", name="CD", attributes=["C", "D"], primary_key=["C"])
    abc = StepRelationInput(node_id="abc", name="ABC", attributes=["A", "B", "C"], primary_key=["A", "B"])
    valid_process = BCNFProcessInput(
        workflow="recursive_decomposition",
        root=root,
        steps=[BCNFDecompositionStepInput(
            step_id="split-d",
            parent_node_id="root",
            selected_fd=FunctionalDependencyInput(lhs=["C"], rhs=["D"]),
            children=[cd, abc],
        )],
    )

    valid = evaluate_recursive_decomposition_process(
        valid_process, {"A", "B", "C", "D"}, dependencies, [cd, abc], "3NF"
    )
    assert valid.valid is True

    bc = StepRelationInput(node_id="bc", name="BC", attributes=["B", "C"], primary_key=["C"])
    acd = StepRelationInput(node_id="acd", name="ACD", attributes=["A", "C", "D"], primary_key=["A", "C"])
    invalid_process = BCNFProcessInput(
        workflow="recursive_decomposition",
        root=root,
        steps=[BCNFDecompositionStepInput(
            step_id="split-b",
            parent_node_id="root",
            selected_fd=FunctionalDependencyInput(lhs=["C"], rhs=["B"]),
            children=[bc, acd],
        )],
    )
    invalid = evaluate_recursive_decomposition_process(
        invalid_process, {"A", "B", "C", "D"}, dependencies, [bc, acd], "3NF"
    )

    assert invalid.valid is False
    assert "dependent is prime" in invalid.errors[0]


def test_3nf_process_rejects_non_equivalent_cover() -> None:
    dependencies = [
        FD(frozenset({"A", "B"}), frozenset({"C"})),
        FD(frozenset({"C"}), frozenset({"B"})),
        FD(frozenset({"C"}), frozenset({"D"})),
    ]
    process = ThreeNFProcessInput(
        workflow="synthesis",
        proposed_minimal_cover=[FunctionalDependencyInput(lhs=["C"], rhs=["D"])],
        synthesis_relations=[SynthesisRelationJustificationInput(relation_name="R2", supporting_fds=[FunctionalDependencyInput(lhs=["C"], rhs=["D"])])],
    )
    relations = [
        RelationInput(name="R1", attributes=["A", "B", "C"], primary_key=["A", "B"]),
        RelationInput(name="R2", attributes=["C", "D"], primary_key=["C"]),
    ]

    result = evaluate_3nf_process(process, {"A", "B", "C", "D"}, dependencies, relations)

    assert result.valid is False
    assert "not logically equivalent" in result.step_results[0].feedback
