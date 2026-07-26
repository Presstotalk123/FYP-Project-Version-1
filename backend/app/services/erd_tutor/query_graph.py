"""Query StateGraph for the ERD tutor engine (Task 6.2).

Wires the two query stages in order:

    START -> tutor -> state_update -> END
"""

from langgraph.graph import StateGraph, START, END
from app.services.erd_tutor.state import GraphState
from app.services.erd_tutor.nodes import tutor_node, state_update_node


def build_query_graph():
    g = StateGraph(GraphState)
    g.add_node("tutor", tutor_node)
    g.add_node("state_update", state_update_node)
    g.add_edge(START, "tutor")
    g.add_edge("tutor", "state_update")
    g.add_edge("state_update", END)
    return g.compile()
