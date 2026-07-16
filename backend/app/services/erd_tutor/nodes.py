"""LangGraph node functions for the ERD tutor engine.

Each node takes the graph ``state`` dict, builds messages from ``prompts``,
calls ``make_llm(stage)`` (optionally ``.with_structured_output(Schema)``),
and writes its output back into the state.

  Submit nodes (Task 5.2):
    observe_node    <- DSL node "Extract ERD 1"  -> ObservationJSON
    normalize_node  <- DSL node "Extract ERD 2"  -> CanonicalERD
    grade_node      <- DSL node "Submit LLM"      -> JudgeResult

  Query nodes (Task 6.1):
    tutor_node        <- DSL node "Query Tutor LLM"        -> plain text
    state_update_node <- DSL node "Query State Updater LLM" -> QueryStateUpdate

NOTE: ``make_llm`` is imported at module scope so tests can monkeypatch
``nodes.make_llm`` and have the node functions pick up the patched factory.
"""

import json
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.erd_tutor.llm import make_llm
from app.services.erd_tutor import prompts
from app.services.erd_tutor.schemas import ObservationJSON, CanonicalERD, JudgeResult, QueryStateUpdate


def _image_block(image_b64):
    return {"type": "image_url", "image_url": {"url": image_b64, "detail": "high"}}


def observe_node(state: dict) -> dict:
    user = [{"type": "text", "text": prompts.OBSERVE_USER.format(problem_statement=state["problem_statement"])}]
    if state.get("image_b64"):
        user.append(_image_block(state["image_b64"]))
    llm = make_llm("observe").with_structured_output(ObservationJSON)
    obs = llm.invoke([SystemMessage(prompts.OBSERVE_SYSTEM), HumanMessage(content=user)])
    return {"observation": obs.model_dump()}


def normalize_node(state: dict) -> dict:
    msg = prompts.NORMALIZE_USER.format(problem_statement=state["problem_statement"],
                                        observation_json=json.dumps(state["observation"], ensure_ascii=False))
    llm = make_llm("normalize").with_structured_output(CanonicalERD)
    can = llm.invoke([SystemMessage(prompts.NORMALIZE_SYSTEM), HumanMessage(msg)])
    return {"canonical_erd": can.model_dump()}


def grade_node(state: dict) -> dict:
    msg = prompts.GRADE_USER.format(
        problem_statement=state["problem_statement"], rubric_json=state["rubric_json"],
        canonical_erd=json.dumps(state["canonical_erd"], ensure_ascii=False),
        last_submit_report=json.dumps(state.get("last_submit_report", {}), ensure_ascii=False),
        ibl_stage=state["ibl_stage"], hint_level=state["hint_level"])
    llm = make_llm("grade").with_structured_output(JudgeResult)
    judge = llm.invoke([SystemMessage(prompts.GRADE_SYSTEM), HumanMessage(msg)])
    return {"judge": judge.model_dump()}


def tutor_node(state: dict) -> dict:
    erd_model = state.get("current_erd_model") or None
    report = state.get("last_submit_report") or {}
    # Compact feedback context: skip the bulky per-check JSON string, keep what
    # the tutor needs to answer "how do I improve?".
    feedback = {k: report[k] for k in ("score", "top_issues", "failed_must_checks", "student_message")
                if report.get(k)} or None
    user = [{"type": "text", "text": prompts.TUTOR_USER.format(
        student_query=state.get("student_query", ""), problem_statement=state["problem_statement"],
        difficulty=state.get("difficulty", ""), rubric=state.get("rubric_json", ""),
        current_erd_model=json.dumps(erd_model, ensure_ascii=False) if erd_model else "null",
        last_submit_feedback=json.dumps(feedback, ensure_ascii=False) if feedback else "null",
        ibl_stage=state["ibl_stage"], hint_level=state["hint_level"])}]
    if state.get("image_b64"):
        user.append(_image_block(state["image_b64"]))
    resp = make_llm("tutor").invoke([SystemMessage(prompts.TUTOR_SYSTEM), HumanMessage(content=user)])
    return {"tutor_text": resp.content}


def state_update_node(state: dict) -> dict:
    msg = prompts.STATE_USER.format(prev_stage=state["ibl_stage"], prev_hint=state["hint_level"],
                                    tutor_text=state["tutor_text"], student_query=state.get("student_query", ""))
    llm = make_llm("state").with_structured_output(QueryStateUpdate)
    upd = llm.invoke([SystemMessage(prompts.STATE_SYSTEM), HumanMessage(msg)])
    return {"state_update": upd.model_dump()}
