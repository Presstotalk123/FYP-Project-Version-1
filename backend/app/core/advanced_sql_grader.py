"""
Grading pipeline for Advanced SQL Testing (triggers / complex DML on SQL
Questions). Unlike standard-mode grading, correctness here can't be verified
by hashing the submitted statement's own output — the submitted SQL (e.g. a
trigger definition) typically returns no rows at all. Instead grading:

  1. Applies the submitted SQL (student's own, or staff's reference
     implementation at save time).
  2. Runs a hidden Test Script that exercises its effect (e.g. an INSERT that
     should fire the trigger).
  3. Runs a hidden Check Query that captures the resulting database state.
  4. Hashes the Check Query's output (same method as standard-mode grading)
     for comparison.

All three steps run against a single isolated, in-memory clone of the
question's database, never the canonical on-disk file.
"""
import sqlite3
import threading
import time
from typing import Tuple, List, Dict, Any

from app.core.answer_validator import generate_hash
from app.core.query_deadline import attach_deadline


class AdvancedGradingError(Exception):
    """
    Raised when a stage of the Advanced SQL Testing pipeline fails.

    `stage` identifies which step failed:
      - "student":     the submitted SQL (student's own, or staff's reference
                        implementation) — safe to show the message verbatim,
                        it describes the submitter's own code.
      - "test_script": the hidden Test Script failed against the submission.
      - "check_query": the hidden Check Query failed.
      - "timeout":      the pipeline exceeded its time budget (message is a
                        fixed, generic string — safe to show verbatim, it
                        never contains hidden-script content).
    Messages for "test_script"/"check_query" must never be shown to students
    verbatim — they can reveal hidden table/column names.
    """

    def __init__(self, stage: str, message: str):
        self.stage = stage
        self.message = message
        super().__init__(message)


_BLOCKED_KEYWORDS = ["ATTACH", "DETACH", "PRAGMA", "VACUUM"]


def is_permissive_but_safe(sql: str, stage: str) -> None:
    """
    Validate SQL submitted for Advanced SQL Testing. Unlike the standard
    SELECT-only QueryExecutor, this allows DDL/DML (CREATE TRIGGER, INSERT,
    UPDATE, DELETE, etc.) since that's the point of this grading mode.

    Still blocks statements that could escape the sandbox and touch the
    server's filesystem directly, regardless of the sandbox being in-memory:
    ATTACH/DETACH (opens another on-disk database file into this connection)
    and VACUUM INTO (writes the database out to an arbitrary path). PRAGMA is
    blocked as a blanket precaution against pragmas that alter
    safety-relevant connection behavior.

    Args:
        sql: The SQL to validate.
        stage: The AdvancedGradingError stage to raise under if invalid.

    Raises:
        AdvancedGradingError: if the SQL is empty or contains a blocked keyword.
    """
    if not sql or not sql.strip():
        raise AdvancedGradingError(stage, "Submitted SQL cannot be empty")

    sql_upper = sql.upper()
    for keyword in _BLOCKED_KEYWORDS:
        if keyword in sql_upper:
            raise AdvancedGradingError(
                stage,
                f"'{keyword}' is not allowed in Advanced SQL Testing submissions"
            )


def validate_check_query(check_query: str) -> None:
    """
    The Check Query must be a single SELECT/WITH statement — it's executed
    via a single cursor.execute() (not executescript()), and only its own
    result set is hashed.

    Raises:
        AdvancedGradingError: (stage="check_query") if invalid.
    """
    if not check_query or not check_query.strip():
        raise AdvancedGradingError("check_query", "Check Query cannot be empty")

    cleaned = check_query.strip()
    upper = cleaned.upper()
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        raise AdvancedGradingError("check_query", "Check Query must be a SELECT statement")

    body = cleaned[:-1] if cleaned.endswith(";") else cleaned
    if ";" in body:
        raise AdvancedGradingError("check_query", "Check Query must be a single SELECT statement")


def run_advanced_pipeline(
    base_db_path: str,
    submitted_sql: str,
    test_script: str,
    check_query: str,
    timeout_seconds: int = 15,
) -> Tuple[List[str], List[Tuple], float]:
    """
    Run the Advanced SQL Testing grading pipeline against an isolated,
    in-memory clone of the question's database.

    The in-memory database is populated via SQLite's online backup API from
    a read-only connection to `base_db_path` — the canonical on-disk file is
    never opened writable, and the sandbox is discarded (freed) the instant
    the in-memory connection closes. Nothing is ever written to disk for a
    grading run.

    All three steps (submitted SQL, Test Script, Check Query) run against the
    SAME in-memory connection so triggers and other side effects created by
    the submitted SQL persist through the later steps.

    Returns:
        Tuple of (columns, rows, execution_time_ms) from the Check Query.

    Raises:
        AdvancedGradingError: tagged with the stage that failed.
    """
    result_container: Dict[str, Any] = {
        "columns": [],
        "results": [],
        "error": None,
        "error_stage": None,
    }

    def run_in_thread():
        source = None
        dest = None
        try:
            source = sqlite3.connect(f"file:{base_db_path}?mode=ro", uri=True)
            dest = sqlite3.connect(":memory:")
            source.backup(dest)
            # Bound the student SQL / test script / check query that run on dest.
            attach_deadline(dest, timeout_seconds)
            source.close()
            source = None

            cursor = dest.cursor()

            try:
                cursor.executescript(submitted_sql)
                dest.commit()
            except sqlite3.Error as e:
                result_container["error"] = str(e)
                result_container["error_stage"] = "student"
                return

            try:
                cursor.executescript(test_script)
                dest.commit()
            except sqlite3.Error as e:
                error_msg = str(e).lower()
                if "syntax error" in error_msg or "no such table" in error_msg or "no such column" in error_msg:
                    result_container["error"] = str(e)
                    result_container["error_stage"] = "test_script"
                    return
                # Otherwise, it is likely a constraint violation or trigger abort (which is expected).
                pass

            try:
                cursor.execute(check_query)
                rows = cursor.fetchall()
                columns = [d[0] for d in cursor.description] if cursor.description else []
            except sqlite3.Error as e:
                result_container["error"] = str(e)
                result_container["error_stage"] = "check_query"
                return

            result_container["columns"] = columns
            result_container["results"] = rows
        finally:
            if dest is not None:
                try:
                    dest.close()
                except Exception:
                    pass
            if source is not None:
                try:
                    source.close()
                except Exception:
                    pass

    start_time = time.time()
    thread = threading.Thread(target=run_in_thread)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout_seconds)
    execution_time_ms = (time.time() - start_time) * 1000

    if thread.is_alive():
        raise AdvancedGradingError(
            "timeout",
            f"Execution exceeded {timeout_seconds} seconds",
        )

    if result_container["error"] is not None:
        raise AdvancedGradingError(result_container["error_stage"], result_container["error"])

    return result_container["columns"], result_container["results"], execution_time_ms


def compute_advanced_hash(columns: List[str], results: List[Tuple]) -> str:
    """Hash a Check Query's output using the same method as standard-mode grading."""
    return generate_hash(results, columns)
