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
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.services.erd_tutor.llm import make_llm
from app.services.erd_tutor import prompts
from app.services.erd_tutor.drawio_parser import parse_drawio
from app.services.erd_tutor.derivation import derive
from app.services.erd_tutor.description_claims import (
    apply_endpoint_claims, merge_objects, read_claims, restamp_provenance,
)

logger = logging.getLogger(__name__)
# Only tutor_system and grade_system are admin-editable (see
# prompt_store.PROMPT_REGISTRY); the other nodes use prompts.* directly.
from app.services.erd_tutor.prompt_store import get_prompt
from app.services.erd_tutor.schemas import ObservationJSON, CanonicalERD, JudgeResult, QueryStateUpdate


def _image_block(image_b64):
    return {"type": "image_url", "image_url": {"url": image_b64, "detail": "high"}}


async def observe_node(state: dict) -> dict:
    # The draw.io source, when we have it, IS the diagram: the PNG is rendered
    # from it, so vision can only lose detail relative to it. Parsing is exact,
    # free and instant, and removes the whole class of extraction defects
    # measured on this pipeline (phantom cues, misread markers, marks binding to
    # a neighbouring connector, invisible thin arcs). Anything unparseable —
    # and every image upload — falls through to the vision path below.
    xml_text = (state.get("submission_xml_text") or "").strip()
    if xml_text:
        try:
            return {"observation": parse_drawio(xml_text)}
        except Exception as exc:
            logger.warning("drawio parse failed (%s); falling back to vision", exc)

    user = [{"type": "text", "text": prompts.OBSERVE_USER.format(problem_statement=state["problem_statement"])}]
    if state.get("image_b64"):
        user.append(_image_block(state["image_b64"]))
    llm = make_llm("observe").with_structured_output(ObservationJSON)
    obs = await llm.ainvoke([SystemMessage(prompts.OBSERVE_SYSTEM), HumanMessage(content=user)])
    return {"observation": obs.model_dump()}


async def normalize_node(state: dict) -> dict:
    observation = state.get("observation")

    # The description is read ONCE and applied in two places, because objects and
    # endpoint values live in different shapes. Objects must be merged before the
    # normalize LLM runs or the canonical model will not contain them — and a
    # described relationship then gets its cardinalities from the same derive()
    # path as a drawn one. Endpoint values must be applied after derive(), or the
    # deterministic pass would overwrite them.
    claims = await read_claims(state.get("submission_description"), observation)
    observation, provenance = merge_objects(observation, claims)

    msg = prompts.NORMALIZE_USER.format(problem_statement=state["problem_statement"],
                                        observation_json=json.dumps(observation, ensure_ascii=False))
    llm = make_llm("normalize").with_structured_output(CanonicalERD)
    can = await llm.ainvoke([SystemMessage(prompts.NORMALIZE_SYSTEM), HumanMessage(msg)])
    out = can.model_dump()
    # The LLM just rewrote that JSON and may have paraphrased away the evidence
    # merge_objects wrote; put the provenance back deterministically, so a mark
    # taken on the student's word stays traceable to the words it came from.
    out = restamp_provenance(out, provenance)

    # Cardinality and participation are a lookup table over the observed marks,
    # not a judgement — so they are computed, not asked for. The LLM keeps the
    # naming/OCR work it is good at. Measured motivation: given exact parser
    # input it returned the same value for two different endpoints of two
    # same-named relationships, discarding a marker the student had drawn
    # correctly. Keyed by id here, so same-named relationships cannot merge.
    #
    # Note this derives from the ENRICHED observation, not state["observation"]:
    # that is what gives a relationship the student only described its endpoints.
    cards, parts = derive(observation)
    if cards:
        cards, parts, applied = apply_endpoint_claims(cards, parts, claims)
        out["cardinalities"], out["participation"] = cards, parts
        if applied:
            logger.info("normalize: %d endpoint value(s) came from the description", applied)
    return {"canonical_erd": out}


def _unreturned_scoring_checks(judge: dict, rubric_json) -> list[str]:
    """Rubric check ids that score points (must/should, points > 0) but are
    absent from the judge's checks array — the signature of a truncated judge.

    Optional/zero-point checks are excluded on purpose: scoring.py renders
    those as not_applicable, so their absence costs the student nothing and is
    not evidence of truncation.
    """
    try:
        rubric = rubric_json if isinstance(rubric_json, dict) else json.loads(rubric_json or "{}")
    except (TypeError, ValueError):
        return []
    if not isinstance(rubric, dict):
        return []
    returned = {str(c.get("id", "")).strip() for c in (judge or {}).get("checks", [])}
    missing = []
    for rc in rubric.get("checks", []) or []:
        cid = str(rc.get("id", "")).strip()
        try:
            points = float(rc.get("points", 0))
        except (TypeError, ValueError):
            points = 0.0
        if (cid and cid not in returned
                and rc.get("requirement_level") in ("must", "should") and points > 0):
            missing.append(cid)
    return missing


async def grade_node(state: dict) -> dict:
    msg = prompts.GRADE_USER.format(
        problem_statement=state["problem_statement"], rubric_json=state["rubric_json"],
        canonical_erd=json.dumps(state["canonical_erd"], ensure_ascii=False),
        last_submit_report=json.dumps(state.get("last_submit_report", {}), ensure_ascii=False),
        ibl_stage=state["ibl_stage"], hint_level=state["hint_level"])
    llm = make_llm("grade").with_structured_output(JudgeResult)
    messages = [SystemMessage(get_prompt("grade_system")), HumanMessage(msg)]
    judge = (await llm.ainvoke(messages)).model_dump()

    # A truncated judge must never become a delivered grade. Measured on q33
    # (attempts 2447/2458, byte-identical drawings): one run returned 2 of 26
    # checks — the model itself reported its output "corrupted mid-evaluation" —
    # and scoring.py's conservative missing-check rule failed the other 24,
    # grading a 74% submission at 14%. One retry recovers the transient case;
    # a second incomplete result raises, which the runner turns into an SSE
    # error: the student is asked to resubmit, nothing is persisted, and a
    # regrade keeps the row's previous grade.
    missing = _unreturned_scoring_checks(judge, state["rubric_json"])
    if missing:
        logger.warning("grade: judge omitted %d scoring check(s) (%s); retrying once",
                       len(missing), ", ".join(missing))
        judge = (await llm.ainvoke(messages)).model_dump()
        missing = _unreturned_scoring_checks(judge, state["rubric_json"])
        if missing:
            raise RuntimeError(
                "Grading failed: the judge returned an incomplete result twice "
                f"(missing checks: {', '.join(missing)}). Please submit again.")
    return {"judge": judge}


def _tutor_messages(state: dict):
    """Build the [System, Human] messages for the tutor LLM.

    Shared by ``tutor_node`` (graph path) and the streaming query runner
    (``runner.stream_er_query``) so both send byte-identical prompts — the only
    difference is invoke vs. astream.
    """
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
    return [SystemMessage(get_prompt("tutor_system")), HumanMessage(content=user)]


async def tutor_node(state: dict) -> dict:
    resp = await make_llm("tutor").ainvoke(_tutor_messages(state))
    return {"tutor_text": resp.content}


async def state_update_node(state: dict) -> dict:
    msg = prompts.STATE_USER.format(prev_stage=state["ibl_stage"], prev_hint=state["hint_level"],
                                    tutor_text=state["tutor_text"], student_query=state.get("student_query", ""))
    llm = make_llm("state").with_structured_output(QueryStateUpdate)
    upd = await llm.ainvoke([SystemMessage(prompts.STATE_SYSTEM), HumanMessage(msg)])
    return {"state_update": upd.model_dump()}
