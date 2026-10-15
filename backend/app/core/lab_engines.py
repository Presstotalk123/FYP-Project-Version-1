"""
Lab-engine registry: one place that knows how each lab type builds, runs and reads its
database.

labs.py used to branch on ``lab.lab_type == "graph"`` at every step (create, update,
execute, schema preview, database state, task answer, order toggle, validate). Adding a
third lab type that way means editing every branch, and missing one is a silent bug.
Each step now asks ``get_lab_engine(lab_type)`` for the right functions instead, so a new
lab type (e.g. vector labs) is one entry in ``LAB_ENGINES``.

Every engine must keep the shared contract the rest of the lab machinery relies on:
templates live at ``get_lab_template_path(lab_id)``, ``execute`` returns the
``{success, columns, results, execution_time_ms, row_count, error_message}`` dict, and
reader errors are raised as ``LabDatabaseError``.
"""
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from app.core.graph_query_executor import execute_graph_query
from app.core.lab_query_executor import execute_lab_query
from app.utils.graph_db_manager import create_graph_template, get_graph_schema_info
from app.utils.lab_db_manager import create_lab_template, get_schema_info


@dataclass(frozen=True)
class LabEngine:
    lab_type: str
    # (lab_id, schema_text, seed_text) -> template path
    create_template: Callable[[int, str, str], str]
    # (db_path, query, timeout) -> result dict
    execute: Callable[..., Dict[str, Any]]
    # db_path -> {"tables": [...]} for the staff schema preview
    schema_info: Callable[[str], dict]
    # db_path -> {"tables": [...]} for a student's live database view
    database_state: Callable[[str], dict]


def _sql_database_state(db_path: str) -> dict:
    """Schema plus row count and the first 20 rows of each table (SQL labs)."""
    schema_data = get_schema_info(db_path)
    tables_with_data = []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for table_info in schema_data["tables"]:
            table_name = table_info["name"]
            cursor = conn.cursor()

            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cursor.fetchone()[0]

            cursor.execute(f"SELECT * FROM {table_name} LIMIT 20")
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            tables_with_data.append({
                "name": table_name,
                "columns": table_info["columns"],
                "create_sql": table_info["create_sql"],
                "row_count": row_count,
                "sample_data": {
                    "columns": columns,
                    "rows": [dict(zip(columns, row)) for row in rows]
                }
            })
            cursor.close()
    finally:
        conn.close()
    return {"tables": tables_with_data}


LAB_ENGINES: Dict[str, LabEngine] = {
    "sql": LabEngine(
        lab_type="sql",
        create_template=create_lab_template,
        execute=execute_lab_query,
        schema_info=get_schema_info,
        database_state=_sql_database_state,
    ),
    "graph": LabEngine(
        lab_type="graph",
        create_template=create_graph_template,
        execute=execute_graph_query,
        schema_info=get_graph_schema_info,
        # graphqlite's schema reader already includes sample data
        database_state=get_graph_schema_info,
    ),
}


def get_lab_engine(lab_type: Optional[str]) -> LabEngine:
    """Return the engine for a lab type. Unknown or missing types fall back to SQL,
    matching the old ``if graph: … else: <sql>`` branches."""
    return LAB_ENGINES.get(lab_type or "sql", LAB_ENGINES["sql"])
