import os
from typing import Any, Dict, List

from graphqlite import Graph

from app.utils.lab_db_manager import (
    get_lab_template_path,
    get_student_session_path,  # noqa: F401  (re-exported for callers)
    LabDatabaseError,
)


def _python_type_to_str(value: Any) -> str:
    if isinstance(value, bool):
        return "Boolean"
    if isinstance(value, int):
        return "Integer"
    if isinstance(value, float):
        return "Float"
    if isinstance(value, str):
        return "String"
    return "Any"


def _execute_cypher_statements(g: Graph, cypher_text: str) -> None:
    """Split on ';' and execute each non-empty Cypher statement."""
    for stmt in cypher_text.split(";"):
        stmt = stmt.strip()
        if stmt:
            g.query(stmt)


def create_graph_template(lab_id: int, schema_cypher: str, seed_cypher: str) -> str:
    """
    Create a graphqlite template database for a graph lab.

    Executes schema_cypher then seed_cypher (both split by ';').
    Validates that at least one node was created.

    Returns:
        Full path to the template .db file.

    Raises:
        LabDatabaseError
    """
    template_path = get_lab_template_path(lab_id)

    # Remove any existing template
    if os.path.exists(template_path):
        try:
            os.remove(template_path)
        except Exception as e:
            raise LabDatabaseError(f"Failed to remove existing template: {e}")

    g = None
    try:
        g = Graph(template_path)

        try:
            _execute_cypher_statements(g, schema_cypher)
        except Exception as e:
            raise LabDatabaseError(f"Graph Cypher execution failed: {e}")

        if seed_cypher.strip():
            try:
                _execute_cypher_statements(g, seed_cypher)
            except Exception as e:
                raise LabDatabaseError(f"Graph seed Cypher failed: {e}")

        stats = g.stats()
        if stats.get("node_count", 0) == 0:
            raise LabDatabaseError(
                "No nodes were created. Check your schema/seed Cypher statements."
            )

        return template_path

    except Exception as e:
        # Clean up on failure
        if g:
            try:
                g.close()
            except Exception:
                pass
        if os.path.exists(template_path):
            try:
                os.remove(template_path)
            except Exception:
                pass
        if isinstance(e, LabDatabaseError):
            raise
        raise LabDatabaseError(f"Unexpected error creating graph template: {e}")
    finally:
        if g:
            try:
                g.close()
            except Exception:
                pass


def get_graph_schema_info(db_path: str) -> Dict[str, List[Dict]]:
    """
    Return schema + sample data for a graphqlite database in the same shape as
    the SQL get_schema_info() / get_session_database_state() output so the
    frontend DatabaseTab and SchemaPreview render without changes.

    Node labels map to "tables". Relationship types are appended after nodes.

    Returns a dict compatible with both SchemaPreview and DatabaseStateResponse:
        {
            "tables": [
                {
                    "name": <label or rel_type>,
                    "columns": [{"name": ..., "type": ..., "notnull": False,
                                 "default_value": None, "pk": False}, ...],
                    "create_sql": "",
                    "row_count": <int>,
                    "sample_data": {"columns": [...], "rows": [...]},
                },
                ...
            ]
        }
    """
    if not os.path.exists(db_path):
        raise LabDatabaseError(f"Graph database file not found: {db_path}")

    g = None
    try:
        g = Graph(db_path)

        # ── Node labels ────────────────────────────────────────────────────────
        label_results = g.query("MATCH (n) RETURN DISTINCT labels(n)")
        # Each row: {'labels(n)': ['Person']}
        labels: List[str] = []
        for row in label_results:
            for label_list in row.values():
                if isinstance(label_list, list):
                    for lbl in label_list:
                        if lbl not in labels:
                            labels.append(lbl)

        tables: List[Dict] = []
        node_lookup: Dict[int, str] = {}

        for label in labels:
            all_nodes = g.get_all_nodes(label)
            sample_nodes = all_nodes[:5]

            # Count total nodes with this label
            count_result = g.query(f"MATCH (n:{label}) RETURN count(n) AS cnt")
            node_count = count_result[0]["cnt"] if count_result else len(all_nodes)

            # Infer property keys and types from sampled nodes
            prop_keys: List[str] = []
            prop_types: Dict[str, str] = {}
            for node in sample_nodes:
                props = node.get("properties") or {}
                for k, v in props.items():
                    if k not in prop_keys:
                        prop_keys.append(k)
                        prop_types[k] = _python_type_to_str(v)

            columns_info = [
                {
                    "name": k,
                    "type": prop_types.get(k, "Any"),
                    "notnull": False,
                    "default_value": None,
                    "pk": False,
                }
                for k in prop_keys
            ]

            # Build sample rows from the node properties
            sample_rows = [
                node.get("properties") or {} for node in sample_nodes
            ]

            tables.append({
                "name": label,
                "columns": columns_info,
                "create_sql": "",
                "row_count": node_count,
                "sample_data": {
                    "columns": prop_keys,
                    "rows": sample_rows,
                },
            })

            # Build node ID → display name while we already have all_nodes loaded
            for node in all_nodes:
                nid = node.get("id")
                props = node.get("properties") or {}
                node_lbs = node.get("labels") or [label]
                display = (
                    props.get("name")
                    or next((str(v) for v in props.values() if isinstance(v, str)), None)
                    or (node_lbs[0] if node_lbs else str(nid))
                )
                if nid is not None:
                    node_lookup[nid] = display

        # ── Relationship types ─────────────────────────────────────────────────
        all_edges = g.get_all_edges()
        rel_type_map: Dict[str, List[Dict]] = {}
        rel_type_counts: Dict[str, int] = {}
        for edge in all_edges:
            r = edge.get("r") or {}
            rel_type = r.get("type", "RELATED")
            rel_type_counts[rel_type] = rel_type_counts.get(rel_type, 0) + 1
            if rel_type not in rel_type_map:
                rel_type_map[rel_type] = []
            if len(rel_type_map[rel_type]) < 5:
                start_id = r.get("startNode")
                end_id = r.get("endNode")
                row = {
                    "from": node_lookup.get(start_id, str(start_id) if start_id is not None else "?"),
                    "to": node_lookup.get(end_id, str(end_id) if end_id is not None else "?"),
                }
                row.update(r.get("properties") or {})
                rel_type_map[rel_type].append(row)

        for rel_type, sample_rows in rel_type_map.items():
            rel_prop_keys: List[str] = []
            rel_prop_types: Dict[str, str] = {}
            for row in sample_rows:
                for k, v in row.items():
                    if k not in ("from", "to") and k not in rel_prop_keys:
                        rel_prop_keys.append(k)
                        rel_prop_types[k] = _python_type_to_str(v)

            prop_keys = ["from", "to"] + rel_prop_keys
            columns_info = [
                {"name": "from", "type": "String", "notnull": False, "default_value": None, "pk": False},
                {"name": "to",   "type": "String", "notnull": False, "default_value": None, "pk": False},
            ] + [
                {
                    "name": k,
                    "type": rel_prop_types.get(k, "Any"),
                    "notnull": False,
                    "default_value": None,
                    "pk": False,
                }
                for k in rel_prop_keys
            ]

            tables.append({
                "name": f":{rel_type}",
                "columns": columns_info,
                "create_sql": "",
                "row_count": rel_type_counts[rel_type],
                "sample_data": {
                    "columns": prop_keys,
                    "rows": sample_rows,
                },
            })

        return {"tables": tables}

    except LabDatabaseError:
        raise
    except Exception as e:
        raise LabDatabaseError(f"Failed to read graph schema: {e}")
    finally:
        if g:
            try:
                g.close()
            except Exception:
                pass
