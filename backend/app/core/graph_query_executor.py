import time
import threading
from typing import Tuple, List, Dict, Any

from graphqlite import Graph


class GraphQueryTimeoutError(Exception):
    pass


class GraphQueryExecutionError(Exception):
    pass


def _serialize_graph_value(value: Any) -> Any:
    """
    Flatten nested node/relationship objects returned by Cypher RETURN n / RETURN r.

    graphqlite returns whole nodes as:
        {'id': <int>, 'labels': ['Person'], 'properties': {'name': 'Alice', ...}}
    and relationships as:
        {'id': <int>, 'type': 'KNOWS', 'startNode': <int>, 'endNode': <int>, 'properties': {...}}

    These are flattened into deterministic dicts so generate_hash() produces
    consistent results regardless of query variable names.
    """
    if isinstance(value, dict):
        # Node object: has 'labels' and 'properties' keys — return only properties
        if 'properties' in value and 'labels' in value:
            props = value.get('properties') or {}
            return {k: _serialize_graph_value(v) for k, v in sorted(props.items())}
        # Relationship object: has 'type' and 'properties' keys
        if 'type' in value and 'properties' in value:
            result = {'_type': value['type']}
            props = value.get('properties') or {}
            result.update({k: _serialize_graph_value(v) for k, v in sorted(props.items())})
            return result
        # Generic dict — sort keys recursively
        return {k: _serialize_graph_value(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [_serialize_graph_value(item) for item in value]
    return value


class GraphQueryExecutor:
    """
    Execute Cypher queries against a graphqlite database with threading-based timeout.
    Returns the same result shape as LabQueryExecutor for drop-in compatibility.
    """

    def __init__(self, db_path: str, timeout_seconds: int = 15):
        self.db_path = db_path
        self.timeout_seconds = timeout_seconds

    def execute_query(self, query: str) -> Tuple[List[str], List[Dict], float]:
        """
        Execute a Cypher query.

        Returns:
            (column_names, result_dicts, execution_time_ms)

        Raises:
            GraphQueryTimeoutError
            GraphQueryExecutionError
        """
        result_container: Dict[str, Any] = {
            'columns': [], 'results': [], 'error': None, 'done': False
        }

        def execute_in_thread():
            g = None
            try:
                g = Graph(self.db_path)
                raw = g.query(query)

                if raw and isinstance(raw[0], dict):
                    # Write queries return a single dict with key 'result'
                    if list(raw[0].keys()) == ['result']:
                        result_container['columns'] = []
                        result_container['results'] = []
                    else:
                        columns = list(raw[0].keys())
                        serialized = []
                        for row in raw:
                            serialized.append(
                                {k: _serialize_graph_value(v) for k, v in row.items()}
                            )
                        result_container['columns'] = columns
                        result_container['results'] = serialized
                else:
                    result_container['columns'] = []
                    result_container['results'] = []

                result_container['done'] = True
            except Exception as e:
                result_container['error'] = e
                result_container['done'] = True
            finally:
                if g:
                    try:
                        g.close()
                    except Exception:
                        pass

        start_time = time.time()
        thread = threading.Thread(target=execute_in_thread)
        thread.daemon = True
        thread.start()
        thread.join(timeout=self.timeout_seconds)

        execution_time_ms = (time.time() - start_time) * 1000

        if thread.is_alive():
            raise GraphQueryTimeoutError(
                f"Cypher query exceeded {self.timeout_seconds} seconds"
            )

        if result_container['error']:
            raise GraphQueryExecutionError(
                f"Cypher execution error: {str(result_container['error'])}"
            )

        return (
            result_container['columns'],
            result_container['results'],
            execution_time_ms,
        )


def execute_graph_query(db_path: str, query: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Execute a Cypher query and return a result dict with the same shape as
    execute_lab_query() so all call sites are interchangeable.
    """
    executor = GraphQueryExecutor(db_path, timeout)
    try:
        columns, results, execution_time = executor.execute_query(query)
        return {
            "success": True,
            "columns": columns,
            "results": results,
            "execution_time_ms": execution_time,
            "row_count": len(results),
            "error_message": None,
        }
    except GraphQueryTimeoutError as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "execution_time_ms": timeout * 1000,
            "row_count": 0,
            "error_message": f"Query timeout: {str(e)}",
        }
    except GraphQueryExecutionError as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "execution_time_ms": 0,
            "row_count": 0,
            "error_message": str(e),
        }
    except Exception as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "execution_time_ms": 0,
            "row_count": 0,
            "error_message": f"Unexpected error: {str(e)}",
        }
