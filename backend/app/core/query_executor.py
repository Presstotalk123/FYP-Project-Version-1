import re
import sqlite3
import threading
import time
from typing import Tuple, List, Dict, Any

from app.core.query_deadline import attach_deadline
from app.core.sql_dialect import to_sqlite


class QueryTimeoutError(Exception):
    """Custom exception for query timeout"""
    pass


class UnsafeQueryError(Exception):
    """Custom exception for unsafe SQL queries"""
    pass


class QueryExecutionError(Exception):
    """Custom exception for query execution errors"""
    pass



# Leading keywords that begin a read-only statement.
_READ_ONLY_LEAD_KEYWORDS = {"SELECT", "WITH", "EXPLAIN", "VALUES"}

# PRAGMAs that only report information and never change database/connection
# behavior. Any other pragma (e.g. journal_mode, writable_schema) is blocked.
_READ_ONLY_PRAGMAS = {
    "table_info", "table_list", "table_xinfo",
    "index_list", "index_info", "index_xinfo",
    "foreign_key_list", "database_list",
    "schema_version", "compile_options",
}

# Keywords that must never appear in a submitted query, checked on word
# boundaries so identifiers like `updated_at` don't false-positive.
_DANGEROUS_KEYWORDS = [
    "DROP", "DELETE", "INSERT", "UPDATE", "ALTER",
    "CREATE", "TRUNCATE", "REPLACE", "ATTACH", "DETACH",
    "VACUUM", "GRANT", "REVOKE",
]
_DANGEROUS_KEYWORDS_PATTERN = re.compile(
    r"\b(?:" + "|".join(_DANGEROUS_KEYWORDS) + r")\b"
)
_PRAGMA_NAME_PATTERN = re.compile(r"^PRAGMA\s+([a-zA-Z_]+)", re.IGNORECASE)


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


    def _is_safe_query(self, query: str) -> bool:
        """
        Check if a query is safe to execute.

        Any read-only statement is allowed: SELECT, WITH ... SELECT (CTEs),
        EXPLAIN, VALUES, and a whitelist of introspection-only PRAGMAs
        (e.g. PRAGMA table_info). Write/DDL statements and anything that
        could escape the read-only connection (ATTACH/DETACH) are blocked.
        The underlying SQLite connection is also opened read-only
        (see execute_in_thread), so this check is defense-in-depth rather
        than the sole safeguard.

        Args:
            query: SQL query string

        Returns:
            True if query is safe, False otherwise
        """
        if not query or not query.strip():
            return False

        cleaned = query.strip()

        # Allow a single trailing semicolon, but reject stacked statements
        # (e.g. "SELECT 1; DROP TABLE x;").
        if cleaned.endswith(";"):
            cleaned = cleaned[:-1].strip()
        if ";" in cleaned:
            return False

        cleaned_upper = cleaned.upper()

        # First whitespace-delimited token determines the statement type.
        first_token = cleaned_upper.split(None, 1)[0] if cleaned_upper else ""

        if first_token == "PRAGMA":
            match = _PRAGMA_NAME_PATTERN.match(cleaned)
            if not match or match.group(1).lower() not in _READ_ONLY_PRAGMAS:
                return False
        elif first_token not in _READ_ONLY_LEAD_KEYWORDS:
            return False

        # Block dangerous keywords anywhere in the statement, on word
        # boundaries so identifiers like `updated_at` aren't false positives.
        if _DANGEROUS_KEYWORDS_PATTERN.search(cleaned_upper):
            return False

        return True

    def execute_query(self, query: str) -> Tuple[List[str], List[Tuple], float]:
        """
        Execute a SQL query with safety checks and timeout.

        Uses threading-based timeout for compatibility with FastAPI async workers
        and Azure App Service deployment.

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
                "Only read-only statements are allowed (SELECT, WITH/CTEs, EXPLAIN, "
                "VALUES, or read-only PRAGMA table/index introspection). "
                "Queries must not contain DROP, DELETE, INSERT, UPDATE, ALTER, CREATE, etc., "
                "and must be a single statement."
            )

        result_container = {'columns': [], 'results': [], 'error': None, 'done': False}

        def execute_in_thread():
            """Execute query in a separate thread"""
            conn = None
            cursor = None
            try:
                # Connect to database in read-only mode
                conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
                attach_deadline(conn, self.timeout_seconds)
                cursor = conn.cursor()

                # Execute query
                cursor.execute(query)
                results = cursor.fetchall()

                # Get column names
                columns = [desc[0] for desc in cursor.description] if cursor.description else []

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
            raise QueryTimeoutError(
                f"Query execution exceeded {self.timeout_seconds} seconds"
            )

        # Check for errors
        if result_container['error']:
            raise QueryExecutionError(f"SQL execution error: {str(result_container['error'])}")

        return (
            result_container['columns'],
            result_container['results'],
            execution_time_ms
        )


def _format_success(columns: List[str], results: List[Tuple], execution_time: float) -> Dict[str, Any]:
    """Shape a successful execution into the response dict the callers expect."""
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
        "error_message": None,
    }


def _format_error(message: str, execution_time_ms: float = 0) -> Dict[str, Any]:
    """Shape a failed execution into the response dict the callers expect."""
    return {
        "success": False,
        "columns": [],
        "results": [],
        "raw_results": [],
        "execution_time_ms": execution_time_ms,
        "row_count": 0,
        "error_message": message,
    }


def execute_student_query(db_path: str, query: str, timeout: int = 5) -> Dict[str, Any]:
    """
    Convenience function to execute a student query and return formatted results.

    If the query fails with a SQL execution error, it may be MySQL-dialect syntax SQLite lacks
    (e.g. `no such function: DATEDIFF`). In that case we transpile it to SQLite and silently
    re-run once; if the rewrite succeeds, its result is returned instead. The rewrite is never
    applied to a working query (it only runs after the original already failed), so correct
    submissions are unaffected. Timeouts and unsafe-query rejections are NOT retried — those
    aren't dialect problems, and a dialect error fails fast rather than timing out.

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
        return _format_success(columns, results, execution_time)
    except UnsafeQueryError as e:
        return _format_error(str(e))
    except QueryTimeoutError as e:
        return _format_error(f"Query timeout: {str(e)}", execution_time_ms=timeout * 1000)
    except QueryExecutionError as e:
        # Possibly a MySQL-only construct. Try a silent SQLite rewrite and re-run once.
        converted = to_sqlite(query)
        if converted is not None:
            try:
                columns, results, execution_time = executor.execute_query(converted)
                return _format_success(columns, results, execution_time)
            except (UnsafeQueryError, QueryTimeoutError, QueryExecutionError):
                pass  # rewrite didn't help — surface the student's original error below
        return _format_error(str(e))
