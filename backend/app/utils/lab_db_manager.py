import sqlite3
import os
import shutil
from pathlib import Path
from typing import Tuple
from app.config import settings


class LabDatabaseError(Exception):
    """Custom exception for lab database operations"""
    pass


def get_lab_template_path(lab_id: int) -> str:
    """
    Get path for lab template database.

    Args:
        lab_id: Lab ID

    Returns:
        Full path to template database
    """
    base_path = Path(settings.LAB_DB_PATH) / "templates"
    os.makedirs(base_path, exist_ok=True)
    return str(base_path / f"lab_{lab_id}_template.db")


def get_student_session_path(lab_id: int, user_id: int) -> str:
    """
    Get path for student session database.

    Args:
        lab_id: Lab ID
        user_id: User ID

    Returns:
        Full path to student session database
    """
    base_path = Path(settings.LAB_DB_PATH) / "sessions"
    os.makedirs(base_path, exist_ok=True)
    return str(base_path / f"lab_{lab_id}_student_{user_id}.db")


def create_lab_template(lab_id: int, schema_sql: str, data_sql: str) -> str:
    """
    Create a template database for a lab.

    Args:
        lab_id: Lab ID
        schema_sql: CREATE TABLE statements
        data_sql: INSERT statements

    Returns:
        Path to the created template database

    Raises:
        LabDatabaseError: If database creation fails
    """
    template_path = get_lab_template_path(lab_id)

    # Remove existing template if it exists
    if os.path.exists(template_path):
        try:
            os.remove(template_path)
        except Exception as e:
            raise LabDatabaseError(f"Failed to remove existing template: {str(e)}")

    try:
        # Create database connection
        conn = sqlite3.connect(template_path)
        cursor = conn.cursor()

        # Execute schema SQL (CREATE TABLE statements)
        try:
            cursor.executescript(schema_sql)
            conn.commit()
        except sqlite3.Error as e:
            conn.close()
            if os.path.exists(template_path):
                os.remove(template_path)
            raise LabDatabaseError(f"Schema SQL execution failed: {str(e)}")

        # Execute data SQL (INSERT statements)
        try:
            cursor.executescript(data_sql)
            conn.commit()
        except sqlite3.Error as e:
            conn.close()
            if os.path.exists(template_path):
                os.remove(template_path)
            raise LabDatabaseError(f"Data SQL execution failed: {str(e)}")

        # Verify the database was created successfully
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            conn.close()
            if os.path.exists(template_path):
                os.remove(template_path)
            raise LabDatabaseError("No tables were created. Check your schema SQL.")

        conn.close()

        return template_path

    except Exception as e:
        # Clean up on any error
        if os.path.exists(template_path):
            try:
                os.remove(template_path)
            except:
                pass
        if isinstance(e, LabDatabaseError):
            raise
        raise LabDatabaseError(f"Unexpected error creating template: {str(e)}")


def copy_template_to_session(lab_id: int, user_id: int) -> str:
    """
    Copy template database to create a student session database.

    Args:
        lab_id: Lab ID
        user_id: User ID

    Returns:
        Path to the created session database

    Raises:
        LabDatabaseError: If copy fails
    """
    template_path = get_lab_template_path(lab_id)
    session_path = get_student_session_path(lab_id, user_id)

    # Verify template exists
    if not os.path.exists(template_path):
        raise LabDatabaseError(f"Template database not found for lab {lab_id}")

    # Remove existing session database if it exists
    if os.path.exists(session_path):
        try:
            os.remove(session_path)
        except Exception as e:
            raise LabDatabaseError(f"Failed to remove existing session database: {str(e)}")

    # Copy template to session
    try:
        shutil.copy2(template_path, session_path)
    except Exception as e:
        raise LabDatabaseError(f"Failed to copy template database: {str(e)}")

    # Verify copy was successful
    if not os.path.exists(session_path):
        raise LabDatabaseError("Session database was not created")

    return session_path


def delete_session_database(db_file_path: str) -> None:
    """
    Delete a student session database file.

    Args:
        db_file_path: Path to the database file to delete
    """
    if os.path.exists(db_file_path):
        try:
            os.remove(db_file_path)
        except Exception as e:
            # Log the error but don't raise - cleanup is best effort
            print(f"Warning: Failed to delete session database {db_file_path}: {str(e)}")


def delete_lab_template(lab_id: int) -> None:
    """
    Delete a lab template database.

    Args:
        lab_id: Lab ID
    """
    template_path = get_lab_template_path(lab_id)

    if os.path.exists(template_path):
        try:
            os.remove(template_path)
        except Exception as e:
            # Log the error but don't raise
            print(f"Warning: Failed to delete template database {template_path}: {str(e)}")


def get_schema_info(db_path: str) -> dict:
    """
    Get schema information from a database for preview.

    Args:
        db_path: Path to the database file

    Returns:
        Dictionary with tables and columns information

    Raises:
        LabDatabaseError: If reading schema fails
    """
    if not os.path.exists(db_path):
        raise LabDatabaseError(f"Database file not found: {db_path}")

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Get all tables
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables_data = cursor.fetchall()

        tables = []
        for table_name, create_sql in tables_data:
            # Get column information
            cursor.execute(f"PRAGMA table_info({table_name});")
            columns_data = cursor.fetchall()

            columns = []
            for col_data in columns_data:
                columns.append({
                    "name": col_data[1],
                    "type": col_data[2],
                    "notnull": bool(col_data[3]),
                    "default_value": col_data[4],
                    "pk": bool(col_data[5])
                })

            tables.append({
                "name": table_name,
                "columns": columns,
                "create_sql": create_sql
            })

        conn.close()

        return {"tables": tables}

    except sqlite3.Error as e:
        raise LabDatabaseError(f"Failed to read schema: {str(e)}")
