import os
import gc
import time
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from app.models.lab_session import LabSession
import logging

logger = logging.getLogger(__name__)


def terminate_session(session: LabSession, db: Session) -> bool:
    """
    Terminate a single session and cleanup resources.

    Args:
        session: LabSession object to terminate
        db: Database session

    Returns:
        True if successful, False otherwise
    """
    try:
        # Delete all query attempts for this session
        from app.models.lab_attempt import LabAttempt

        deleted_count = db.query(LabAttempt).filter(
            LabAttempt.session_id == session.id
        ).delete(synchronize_session=False)

        logger.info(f"Deleted {deleted_count} query attempts for session {session.id}")

        # Update session record
        session.is_active = 0
        session.ended_at = datetime.utcnow()
        db.commit()

        # Force garbage collection to close any lingering SQLite connections
        gc.collect()

        # Delete database file if exists - with retry for Windows file locking
        if os.path.exists(session.db_file_path):
            max_retries = 5
            retry_delay = 0.1  # 100ms

            for attempt in range(max_retries):
                try:
                    os.remove(session.db_file_path)
                    logger.info(f"Deleted session DB: {session.db_file_path}")
                    return True
                except PermissionError as e:
                    # File is locked - wait and retry
                    if attempt < max_retries - 1:
                        logger.warning(f"File locked, retry {attempt + 1}/{max_retries}: {session.db_file_path}")
                        time.sleep(retry_delay)
                        gc.collect()  # Try garbage collection again
                        continue
                    else:
                        logger.error(f"Failed to delete DB after {max_retries} attempts: {session.db_file_path}: {e}")
                        # Session is marked inactive, file cleanup failed but don't fail the whole operation
                        return True  # Return True since session is terminated in DB
                except Exception as e:
                    logger.error(f"Failed to delete DB {session.db_file_path}: {e}")
                    return True  # Return True since session is terminated in DB

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
