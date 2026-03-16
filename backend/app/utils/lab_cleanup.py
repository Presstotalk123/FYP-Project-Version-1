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
    Terminate a single session and cleanup resources.
    Query history is preserved for learning analytics and student review.

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

        # Delete database file if exists - using retry logic for Windows file locking
        if os.path.exists(session.db_file_path):
            delete_success = delete_session_file_with_retry(session.db_file_path)
            if not delete_success:
                logger.warning(
                    f"Session {session.id} marked inactive but file deletion failed: "
                    f"{session.db_file_path}"
                )
            # Return True because session is marked inactive in DB regardless of file deletion
            return True

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
    Clean up session database files that have no active session record.
    Run periodically via cron or scheduler.

    Args:
        db: Database session
        lab_db_path: Base path to lab databases

    Returns:
        Number of files cleaned up
    """
    from pathlib import Path

    session_dir = Path(lab_db_path) / "sessions"
    if not session_dir.exists():
        return 0

    cleaned_count = 0

    # Get all active session file paths
    active_sessions = db.query(LabSession.db_file_path).filter(
        LabSession.is_active == 1
    ).all()
    active_paths = {session[0] for session in active_sessions}

    # Check all files in session directory
    for file_path in session_dir.glob("lab_*_student_*.db"):
        full_path = str(file_path)

        # If file not in active sessions, delete it
        if full_path not in active_paths:
            try:
                os.remove(full_path)
                logger.info(f"Cleaned up orphan file: {full_path}")
                cleaned_count += 1
            except Exception as e:
                logger.error(f"Failed to delete orphan file {full_path}: {e}")

    return cleaned_count
