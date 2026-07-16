from typing import Optional, TypedDict

class GraphState(TypedDict, total=False):
    # inputs
    mode: str                      # "Submit" | "Query"
    problem_statement: str
    difficulty: str
    rubric_json: str
    # WIP (post-migration feature): free-text description of the submission,
    # not yet consumed by any node. Replaces the never-read submission_xml
    # field; XML handling will be planned once the migration is complete.
    submission_description: Optional[str]
    image_b64: Optional[str]       # data-url payload, or None
    student_query: Optional[str]
    # carried conversation state
    ibl_stage: str
    hint_level: int
    misconceptions: list
    current_erd_model: dict
    last_submit_report: dict
    # stage outputs
    observation: dict
    canonical_erd: dict
    judge: dict
    result: dict                   # SubmitResult dict (submit) — emitted in SSE
    tutor_text: str                # query
    state_update: dict             # query
