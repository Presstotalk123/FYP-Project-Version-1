from typing import Optional, TypedDict

class GraphState(TypedDict, total=False):
    # inputs
    mode: str                      # "Submit" | "Query"
    problem_statement: str
    difficulty: str
    rubric_json: str
    # Free-text description of the submission (disambiguation support for observe).
    submission_description: Optional[str]
    # draw.io source for the submission. When present and parseable it is the
    # authoritative structure — the PNG is rendered FROM it, so vision can only
    # lose detail relative to it. observe_node parses this and skips the vision
    # call; image uploads and unparseable XML fall back to vision.
    submission_xml_text: Optional[str]
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
