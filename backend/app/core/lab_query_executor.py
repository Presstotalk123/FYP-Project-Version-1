import sqlite3
import time
import threading
from typing import Tuple, List, Dict, Any


class LabQueryTimeoutError(Exception):
    """Custom exception for lab query timeout"""
    pass


class LabQueryExecutionError(Exception):
    """Custom exception for query execution errors"""
    pass


class LabQueryExecutor:
    """
    Execute SQL queries for lab sessions with ALL statements allowed.
    Uses threading-based timeout for Windows compatibility.
    """

    def __init__(self, db_path: str, timeout_seconds: int = 15):
        """
        Initialize lab query executor.

        Args:
            db_path: Path to the SQLite database
            timeout_seconds: Maximum execution time in seconds (default 15)
        """
        self.db_path = db_path
        self.timeout_seconds = timeout_seconds

    def execute_query(self, query: str) -> Tuple[List[str], List[Tuple], float]:
        """
        Execute SQL query with timeout - allows ALL SQL statements.

        Args:
            query: SQL query to execute

        Returns:
            Tuple of (column_names, results, execution_time_ms)

        Raises:
            LabQueryTimeoutError: If query exceeds timeout
            LabQueryExecutionError: For SQL execution errors
        """
        result_container = {'columns': [], 'results': [], 'error': None, 'done': False}

        def execute_in_thread():
            conn = None
            cursor = None
            try:
                # Read-write connection for lab sessions
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # Execute query (all statements allowed)
                cursor.execute(query)

                # Handle different query types
                if query.strip().upper().startswith('SELECT'):
                    results = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                else:
                    # For INSERT, UPDATE, DELETE, CREATE, etc.
                    conn.commit()
                    results = []
                    columns = []

                result_container['columns'] = columns
                result_container['results'] = results
                result_container['done'] = True

            except Exception as e:
                result_container['error'] = e
                result_container['done'] = True
            finally:
                # Always close cursor and connection
                if cursor:
                    try:
                        cursor.close()
                    except:
                        pass
                if conn:
                    try:
                        conn.close()
                    except:
                        pass

        # Execute in thread with timeout
        start_time = time.time()
        thread = threading.Thread(target=execute_in_thread)
        thread.daemon = True
        thread.start()
        thread.join(timeout=self.timeout_seconds)

        execution_time_ms = (time.time() - start_time) * 1000

        # Check timeout
        if thread.is_alive():
            # Query still running - timeout
            raise LabQueryTimeoutError(
                f"Query execution exceeded {self.timeout_seconds} seconds"
            )

        # Check for errors
        if result_container['error']:
            raise LabQueryExecutionError(f"SQL execution error: {str(result_container['error'])}")

        return (
            result_container['columns'],
            result_container['results'],
            execution_time_ms
        )


def execute_lab_query(db_path: str, query: str, timeout: int = 15) -> Dict[str, Any]:
    """
    Execute lab query and return formatted results.
    Convenience function for lab query execution.

    Args:
        db_path: Path to the SQLite database
        query: SQL query to execute
        timeout: Timeout in seconds

    Returns:
        Dictionary with results and metadata
    """
    executor = LabQueryExecutor(db_path, timeout)

    try:
        columns, results, execution_time = executor.execute_query(query)

        # Convert to dict format
        result_dicts = []
        for row in results:
            row_dict = {columns[i]: row[i] for i in range(len(columns))}
            result_dicts.append(row_dict)

        return {
            "success": True,
            "columns": columns,
            "results": result_dicts,
            "execution_time_ms": execution_time,
            "row_count": len(results),
            "error_message": None
        }
    except LabQueryTimeoutError as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "execution_time_ms": timeout * 1000,
            "row_count": 0,
            "error_message": f"Query timeout: {str(e)}"
        }
    except LabQueryExecutionError as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "execution_time_ms": 0,
            "row_count": 0,
            "error_message": str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "execution_time_ms": 0,
            "row_count": 0,
            "error_message": f"Unexpected error: {str(e)}"
        }
