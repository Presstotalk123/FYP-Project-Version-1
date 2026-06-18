import os
import shutil
import sqlite3
from pathlib import Path

from app.config import settings
from app.utils.lab_db_manager import LabDatabaseError  # reuse the exception type


def _dir(sub: str) -> Path:
    p = Path(settings.LAB_DB_PATH) / "sqllab" / sub
    os.makedirs(p, exist_ok=True)
    return p


def get_sqllab_template_path(question_id: int) -> str:
    return str(_dir("templates") / f"sqllab_q_{question_id}_template.db")


def get_sqllab_session_path(session_id: int, item_id: int) -> str:
    return str(_dir("sessions") / f"sqllab_sess_{session_id}_item_{item_id}.db")


def create_sqllab_template(question_id: int, schema_sql: str, data_sql: str) -> str:
    """Build the question's template DB. Raises LabDatabaseError on bad SQL."""
    template_path = get_sqllab_template_path(question_id)
    if os.path.exists(template_path):
        os.remove(template_path)
    try:
        conn = sqlite3.connect(template_path)
        cur = conn.cursor()
        try:
            cur.executescript(schema_sql)
            conn.commit()
        except sqlite3.Error as e:
            conn.close(); os.remove(template_path)
            raise LabDatabaseError(f"Schema SQL execution failed: {str(e)}")
        try:
            cur.executescript(data_sql)
            conn.commit()
        except sqlite3.Error as e:
            conn.close(); os.remove(template_path)
            raise LabDatabaseError(f"Data SQL execution failed: {str(e)}")
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        if not cur.fetchall():
            conn.close(); os.remove(template_path)
            raise LabDatabaseError("No tables were created. Check your schema SQL.")
        conn.close()
        return template_path
    except Exception:
        if os.path.exists(template_path):
            try:
                os.remove(template_path)
            except OSError:
                pass
        raise


def ensure_sqllab_session(question_id: int, session_id: int, item_id: int) -> str:
    """Return the per-(session,item) writable DB path, copying the template on FIRST use only
    (state persists across runs/tasks)."""
    session_path = get_sqllab_session_path(session_id, item_id)
    if os.path.exists(session_path):
        return session_path
    template_path = get_sqllab_template_path(question_id)
    if not os.path.exists(template_path):
        raise LabDatabaseError(f"Template database not found for sql-lab question {question_id}")
    shutil.copy2(template_path, session_path)
    return session_path


def get_sqllab_practice_path(question_id: int, user_id: int) -> str:
    return str(_dir("practice") / f"sqllab_q_{question_id}_u_{user_id}.db")


def ensure_sqllab_practice_session(question_id: int, user_id: int) -> str:
    """Return the per-(question,user) STANDALONE practice DB path (solving outside any lab),
    copying the template on FIRST use only — state persists across runs/tasks and is resumable."""
    practice_path = get_sqllab_practice_path(question_id, user_id)
    if os.path.exists(practice_path):
        return practice_path
    template_path = get_sqllab_template_path(question_id)
    if not os.path.exists(template_path):
        raise LabDatabaseError(f"Template database not found for sql-lab question {question_id}")
    shutil.copy2(template_path, practice_path)
    return practice_path


def _safe_remove(path: str) -> None:
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError as e:
            raise LabDatabaseError(f"Could not reset database (file in use): {e}")


def reset_sqllab_practice(question_id: int, user_id: int) -> None:
    """Discard a student's standalone practice DB so the next run re-seeds from the template."""
    _safe_remove(get_sqllab_practice_path(question_id, user_id))


def reset_sqllab_session(session_id: int, item_id: int) -> None:
    """Discard a student's in-lab item DB so the next run re-seeds from the template."""
    _safe_remove(get_sqllab_session_path(session_id, item_id))


def introspect_db(db_path: str, sample_limit: int = 20) -> dict:
    """Return the current state of a SQLite DB — every user table with its columns,
    row count, and a sample of rows. Used to render the live 'Database' browser."""
    if not os.path.exists(db_path):
        return {"tables": []}
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
        names = [r[0] for r in cur.fetchall()]
        tables = []
        for name in names:
            info = cur.execute(f'PRAGMA table_info("{name}")').fetchall()
            columns = [{"name": c[1], "type": c[2] or ""} for c in info]
            col_names = [c[1] for c in info]
            row_count = cur.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            rows = cur.execute(f'SELECT * FROM "{name}" LIMIT {int(sample_limit)}').fetchall()
            sample = [{col_names[i]: row[i] for i in range(len(col_names))} for row in rows]
            tables.append({"name": name, "columns": columns, "row_count": row_count, "sample_rows": sample})
        return {"tables": tables}
    finally:
        conn.close()
