from app.services.lab_items.base import LabItemHandler
from app.services.lab_items.sql_handler import SqlItemHandler
from app.services.lab_items.sqllab_handler import SqlLabSectionHandler
from app.services.lab_items.graph_handler import GraphItemHandler
from app.services.lab_items.erd_handler import ErdItemHandler

HANDLERS: dict[str, LabItemHandler] = {
    "sql": SqlItemHandler(),
    "sqllab": SqlLabSectionHandler(),
    "graph": GraphItemHandler(),
    "erd": ErdItemHandler(),
}


def get_handler(kind: str) -> LabItemHandler:
    handler = HANDLERS.get(kind)
    if handler is None:
        raise ValueError(f"Unknown lab item kind: {kind}")
    return handler
