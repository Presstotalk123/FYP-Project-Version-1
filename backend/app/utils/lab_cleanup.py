import os
import gc
import time
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from app.models.lab_session import LabSession
import logging

logger = logging.getLogger(__name__)


def delete_session_file_with_retry(db_file_path: str, max_retries: int = 10) -> bool:
    """
    Delete session database file with exponential backoff retry.
    Handles Windows file locking issues.

    Args:
        db_file_path: Path to database file
        max_retries: Maximum retry attempts (default: 10)

    Returns:
        True if deleted or file doesn't exist, False if still locked after all retries
    """
    if not os.path.exists(db_file_path):
        return True

    base_delay = 0.1  # 100ms

    for attempt in range(max_retries):
        # Force garbage collection to release file handles
        gc.collect()

        try:
            os.remove(db_file_path)
            logger.info(f"Deleted session DB: {db_file_path}")
            return True
        except PermissionError as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"File locked, retry {attempt + 1}/{max_retries} "
                    f"after {delay:.2f}s: {db_file_path}"
                )
                time.sleep(delay)
                continue
            else:
                logger.error(
                    f"Failed to delete DB after {max_retries} attempts: "
                    f"{db_file_path}: {e}"
                )
                return False
        except Exception as e:
            logger.error(f"Unexpected error deleting DB {db_file_path}: {e}")
            return False

    return False


def terminate_session(session: LabSession, db: Session) -> bool:
    """
    Terminate a single session.
    Query history is preserved for learning analytics and student review.

    Per-item SQL-lab databases are keyed by (session, item) and cleaned up
    separately; a session no longer owns a single shared DB file.

    Args:
        session: LabSession object to terminate
        db: Database session

    Returns:
        True if successful, False otherwise
    """
    try:
        # Update session record (query attempts are preserved for history)
        session.is_active = 0
        session.ended_at = datetime.utcnow()
        db.commit()

        logger.info(f"Terminated session {session.id}, query history preserved")
        return True
    except Exception as e:
        logger.error(f"Failed to terminate session {session.id}: {e}")
        db.rollback()
        return False


def terminate_all_lab_sessions(lab_id: int, db: Session) -> int:
    """
    Terminate all active sessions for a lab.

    Args:
        lab_id: Lab ID
        db: Database session

    Returns:
        Number of sessions terminated
    """
    active_sessions = db.query(LabSession).filter(
        LabSession.lab_id == lab_id,
        LabSession.is_active == 1
    ).all()

    terminated_count = 0
    for session in active_sessions:
        if terminate_session(session, db):
            terminated_count += 1

    return terminated_count


def cleanup_orphan_session_files(db: Session, lab_db_path: str) -> int:
    """
    Clean up per-(session, item) SQL-lab database files whose session is no
    longer active. Run periodically via cron or scheduler.

    Session DB files are named ``sqllab_sess_{session_id}_item_{item_id}.db``
    under ``{lab_db_path}/sqllab/sessions``. A file is orphaned when its
    session id has no active LabSession row.

    Args:
        db: Database session
        lab_db_path: Base path to lab databases

    Returns:
        Number of files cleaned up
    """
    import re
    from pathlib import Path

    session_dir = Path(lab_db_path) / "sqllab" / "sessions"
    if not session_dir.exists():
        return 0

    active_ids = {
        sid for (sid,) in db.query(LabSession.id).filter(LabSession.is_active == 1).all()
    }

    cleaned_count = 0
    pattern = re.compile(r"sqllab_sess_(\d+)_item_\d+\.db$")
    for file_path in session_dir.glob("sqllab_sess_*_item_*.db"):
        m = pattern.search(file_path.name)
        if m and int(m.group(1)) in active_ids:
            continue
        try:
            os.remove(str(file_path))
            logger.info(f"Cleaned up orphan file: {file_path}")
            cleaned_count += 1
        except Exception as e:
            logger.error(f"Failed to delete orphan file {file_path}: {e}")

    return cleaned_count
