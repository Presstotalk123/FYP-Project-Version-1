import sqlite3
import signal
import time
from contextlib import contextmanager
from typing import Tuple, List, Dict, Any


class QueryTimeoutError(Exception):
    """Custom exception for query timeout"""
    pass


class UnsafeQueryError(Exception):
    """Custom exception for unsafe SQL queries"""
    pass


class QueryExecutionError(Exception):
    """Custom exception for query execution errors"""
    pass


class QueryExecutor:
    """
    Execute SQL queries with safety checks and timeout.
    """

    def __init__(self, db_path: str, timeout_seconds: int = 5):
        """
        Initialize query executor.

        Args:
            db_path: Path to the SQLite database
            timeout_seconds: Maximum execution time in seconds
        """
        self.db_path = db_path
        self.timeout_seconds = timeout_seconds

    @contextmanager
    def _timeout_handler(self):
        """
        Context manager for query timeout using signal.alarm.
        Note: signal.alarm only works on Unix systems. On Windows, we'll use a different approach.
        """
        def timeout_handler_func(signum, frame):
            raise QueryTimeoutError(f"Query execution exceeded {self.timeout_seconds} seconds")

        # Try to use signal.alarm (Unix only)
        try:
            old_handler = signal.signal(signal.SIGALRM, timeout_handler_func)
            signal.alarm(self.timeout_seconds)
            try:
                yield
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except AttributeError:
            # Windows doesn't support SIGALRM, so we just yield without timeout
            # In production, consider using threading.Timer or multiprocessing
            yield

    def _is_safe_query(self, query: str) -> bool:
        """
        Check if a query is safe to execute.
        Only SELECT queries are allowed.

        Args:
            query: SQL query string

        Returns:
            True if query is safe, False otherwise
        """
        if not query or not query.strip():
            return False

        # Remove leading/trailing whitespace and convert to uppercase
        query_upper = query.strip().upper()

        # Must start with SELECT
        if not query_upper.startswith("SELECT"):
            return False

        # Block dangerous keywords
        dangerous_keywords = [
            "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
            "CREATE", "TRUNCATE", "REPLACE", "PRAGMA",
            "ATTACH", "DETACH"
        ]

        for keyword in dangerous_keywords:
            if keyword in query_upper:
                return False

        return True

    def execute_query(self, query: str) -> Tuple[List[str], List[Tuple], float]:
        """
        Execute a SQL query with safety checks and timeout.

        Args:
            query: SQL query to execute

        Returns:
            Tuple of (column_names, results, execution_time_ms)

        Raises:
            UnsafeQueryError: If query contains unsafe operations
            QueryTimeoutError: If query execution times out
            QueryExecutionError: If query execution fails
        """
        # Validate query safety
        if not self._is_safe_query(query):
            raise UnsafeQueryError(
                "Only SELECT queries are allowed. "
                "Queries must not contain DROP, DELETE, INSERT, UPDATE, ALTER, CREATE, etc."
            )

        try:
            # Connect to database in read-only mode
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            cursor = conn.cursor()

            # Execute query with timeout
            start_time = time.time()

            with self._timeout_handler():
                cursor.execute(query)
                results = cursor.fetchall()

            execution_time_ms = (time.time() - start_time) * 1000

            # Get column names
            column_names = [description[0] for description in cursor.description] if cursor.description else []

            cursor.close()
            conn.close()

            return column_names, results, execution_time_ms

        except QueryTimeoutError:
            raise
        except sqlite3.Error as e:
            raise QueryExecutionError(f"SQL execution error: {str(e)}")
        except Exception as e:
            raise QueryExecutionError(f"Unexpected error during query execution: {str(e)}")


def execute_student_query(db_path: str, query: str, timeout: int = 5) -> Dict[str, Any]:
    """
    Convenience function to execute a student query and return formatted results.

    Args:
        db_path: Path to the SQLite database
        query: SQL query to execute
        timeout: Timeout in seconds

    Returns:
        Dictionary with results and metadata
    """
    executor = QueryExecutor(db_path, timeout)

    try:
        columns, results, execution_time = executor.execute_query(query)

        # Convert results to list of dictionaries
        result_dicts = []
        for row in results:
            row_dict = {columns[i]: row[i] for i in range(len(columns))}
            result_dicts.append(row_dict)

        return {
            "success": True,
            "columns": columns,
            "results": result_dicts,
            "raw_results": results,  # Keep raw tuples for hash generation
            "execution_time_ms": execution_time,
            "row_count": len(results),
            "error_message": None
        }

    except UnsafeQueryError as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "raw_results": [],
            "execution_time_ms": 0,
            "row_count": 0,
            "error_message": str(e)
        }
    except QueryTimeoutError as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "raw_results": [],
            "execution_time_ms": timeout * 1000,
            "row_count": 0,
            "error_message": f"Query timeout: {str(e)}"
        }
    except QueryExecutionError as e:
        return {
            "success": False,
            "columns": [],
            "results": [],
            "raw_results": [],
            "execution_time_ms": 0,
            "row_count": 0,
            "error_message": str(e)
        }
