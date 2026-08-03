"""Cooperative statement-level deadlines for SQLite-backed query executors.

The executors run user queries in a daemon thread and rely on
``thread.join(timeout=...)`` for their timeout. That only stops *waiting* — the
abandoned worker thread keeps running the SQLite statement to completion,
pinning a CPU core (and holding a connection) long after the client has already
received a timeout error.

``attach_deadline`` registers a SQLite progress handler that returns non-zero
once the deadline passes, which makes the in-flight statement raise
``sqlite3.OperationalError`` and lets the worker thread exit and free the CPU.

A small grace period is added on top of the executor's own timeout so the
executor's ``join`` still wins the race and reports its clean timeout error; the
handler then reclaims the abandoned thread shortly afterwards instead of never.
"""
import time

# SQLite invokes the handler roughly every N virtual-machine instructions.
# 10k gives sub-millisecond cancellation granularity at negligible (<0.1%)
# overhead on normal queries.
_PROGRESS_INSTRUCTION_INTERVAL = 10_000

# Let the executor's own join(timeout=...) fire first so the client still
# receives the executor's timeout error; the handler then kills the abandoned
# thread this many seconds later.
_DEFAULT_GRACE_SECONDS = 2.0


def attach_deadline(conn, timeout_seconds, grace_seconds=_DEFAULT_GRACE_SECONDS):
    """Abort in-flight statements on ``conn`` once the deadline elapses.

    Args:
        conn: A ``sqlite3.Connection``.
        timeout_seconds: The executor's own timeout; the handler deadline is set
            to this plus ``grace_seconds`` so the executor reports the timeout
            first and the handler only reclaims the abandoned thread.
        grace_seconds: Extra time granted before the statement is aborted.
    """
    deadline = time.monotonic() + timeout_seconds + grace_seconds

    def _abort_if_expired():
        return 1 if time.monotonic() > deadline else 0

    conn.set_progress_handler(_abort_if_expired, _PROGRESS_INSTRUCTION_INTERVAL)
