"""Submit StateGraph for the ERD tutor engine (Task 5.3).

Wires the four submit stages in order:

    START -> observe -> normalize -> grade -> score -> END

``observe_node`` / ``normalize_node`` / ``grade_node`` and ``compute_grade``
are imported at *module scope* so tests can monkeypatch them by attribute
(``monkeypatch.setattr(submit_graph, "observe_node", ...)`` etc.) and have the
compiled graph pick up the patched callables.
"""

from langgraph.graph import StateGraph, START, END
from app.services.erd_tutor.state import GraphState
from app.services.erd_tutor.nodes import observe_node, normalize_node, grade_node
from app.services.erd_tutor.scoring import compute_grade


def _score_node(state: dict) -> dict:
    return {"result": compute_grade(state["judge"], _as_dict(state["rubric_json"]),
                                    state.get("last_submit_report", {}))}


def _as_dict(rubric_json):
    import json
    if isinstance(rubric_json, dict): return rubric_json
    try: return json.loads(rubric_json or "{}")
    except Exception: return {}


def build_submit_graph():
    g = StateGraph(GraphState)
    g.add_node("observe", observe_node)
    g.add_node("normalize", normalize_node)
    g.add_node("grade", grade_node)
    g.add_node("score", _score_node)
    g.add_edge(START, "observe")
    g.add_edge("observe", "normalize")
    g.add_edge("normalize", "grade")
    g.add_edge("grade", "score")
    g.add_edge("score", END)
    return g.compile()
