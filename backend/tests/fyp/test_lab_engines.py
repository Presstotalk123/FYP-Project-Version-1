"""Unit tests for the lab-engine registry (app/core/lab_engines.py)."""
from app.core import lab_engines
from app.core.lab_engines import LAB_ENGINES, get_lab_engine


def test_registered_lab_types():
    assert set(LAB_ENGINES) == {"sql", "graph"}
    for lab_type, engine in LAB_ENGINES.items():
        assert engine.lab_type == lab_type


def test_unknown_or_missing_type_falls_back_to_sql():
    # Mirrors the inherited `if graph: … else: <sql>` behaviour.
    assert get_lab_engine(None) is LAB_ENGINES["sql"]
    assert get_lab_engine("") is LAB_ENGINES["sql"]
    assert get_lab_engine("not-a-type") is LAB_ENGINES["sql"]


def test_graph_engine_uses_graph_functions():
    from app.core.graph_query_executor import execute_graph_query
    from app.utils.graph_db_manager import create_graph_template, get_graph_schema_info

    g = get_lab_engine("graph")
    assert g.create_template is create_graph_template
    assert g.execute is execute_graph_query
    assert g.schema_info is get_graph_schema_info


def test_labs_router_has_no_lab_type_branches():
    """Guard against new `== "graph"` branches creeping back into the router."""
    import inspect
    from app.api.v1.endpoints import labs

    source = inspect.getsource(labs)
    assert '== "graph"' not in source
    assert "execute_graph_query" not in source


def test_sql_database_state_reports_rows(tmp_path):
    import sqlite3

    db = tmp_path / "s.db"
    conn = sqlite3.connect(db)
    conn.executescript("CREATE TABLE t (a INTEGER); INSERT INTO t VALUES (1),(2),(3);")
    conn.close()

    state = lab_engines._sql_database_state(str(db))
    (table,) = state["tables"]
    assert table["name"] == "t"
    assert table["row_count"] == 3
    assert table["sample_data"]["rows"] == [{"a": 1}, {"a": 2}, {"a": 3}]
