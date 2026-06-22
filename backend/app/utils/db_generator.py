import sqlite3
import uuid
import os
from typing import Tuple, List, Dict, Any
from pathlib import Path
from app.config import settings


class SQLValidationError(Exception):
    """Custom exception for SQL validation errors"""
    pass


class DatabaseGenerationError(Exception):
    """Custom exception for database generation errors"""
    pass


def get_question_db_path(db_filename: str) -> str:
    """
    Get the full path for a question database file.

    Args:
        db_filename: The database filename

    Returns:
        Full path to the database file
    """
    base_path = Path(settings.QUESTION_DB_PATH)
    return str(base_path / db_filename)


def generate_unique_filename() -> str:
    """
    Generate a unique filename for a question database.

    Returns:
        Unique filename with .db extension
    """
    return f"{uuid.uuid4()}.db"


def validate_sql_statements(sql: str, statement_type: str = "general") -> None:
    """
    Basic validation of SQL statements.

    Args:
        sql: SQL statement(s) to validate
        statement_type: Type of statement (schema, data, query)

    Raises:
        SQLValidationError: If SQL is invalid or contains dangerous operations
    """
    if not sql or not sql.strip():
        raise SQLValidationError(f"{statement_type} SQL cannot be empty")

    sql_upper = sql.upper()

    # Check for dangerous operations in schema/data SQL
    if statement_type in ["schema", "data"]:
        dangerous_keywords = ["DROP DATABASE", "DROP SCHEMA"]
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                raise SQLValidationError(f"Dangerous operation detected: {keyword}")

    # For queries, only allow SELECT
    if statement_type == "query":
        # Remove comments and whitespace
        cleaned_sql = sql.strip()
        if not cleaned_sql.upper().startswith("SELECT"):
            raise SQLValidationError("Only SELECT queries are allowed for answer validation")


def create_sqlite_from_sql(
    schema_sql: str,
    data_sql: str,
    correct_answer_query: str
) -> Tuple[str, str]:
    """
    Create a SQLite database file from SQL statements and return the filepath and database filename.

    Args:
        schema_sql: CREATE TABLE statements
        data_sql: INSERT statements
        correct_answer_query: SELECT query to validate (not executed here, just validated)

    Returns:
        Tuple of (db_filename, full_db_path)

    Raises:
        SQLValidationError: If SQL validation fails
        DatabaseGenerationError: If database creation fails
    """
    # Validate SQL statements
    validate_sql_statements(schema_sql, "schema")
    validate_sql_statements(data_sql, "data")
    validate_sql_statements(correct_answer_query, "query")

    # Generate unique filename
    db_filename = generate_unique_filename()
    db_path = get_question_db_path(db_filename)

    # Ensure the directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    try:
        # Create database connection
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Execute schema SQL (CREATE TABLE statements)
        try:
            cursor.executescript(schema_sql)
            conn.commit()
        except sqlite3.Error as e:
            conn.close()
            # Clean up the file if it was created
            if os.path.exists(db_path):
                os.remove(db_path)
            raise DatabaseGenerationError(f"Schema SQL execution failed: {str(e)}")

        # Execute data SQL (INSERT statements)
        try:
            cursor.executescript(data_sql)
            conn.commit()
        except sqlite3.Error as e:
            conn.close()
            # Clean up the file
            if os.path.exists(db_path):
                os.remove(db_path)
            raise DatabaseGenerationError(f"Data SQL execution failed: {str(e)}")

        # Verify the database was created successfully
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()

        if not tables:
            conn.close()
            if os.path.exists(db_path):
                os.remove(db_path)
            raise DatabaseGenerationError("No tables were created. Check your schema SQL.")

        conn.close()

        return db_filename, db_path

    except Exception as e:
        # Clean up on any error
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except:
                pass
        raise


def execute_query_on_database(db_path: str, query: str) -> Tuple[List[str], List[Tuple]]:
    """
    Execute a query on a SQLite database and return results.

    Args:
        db_path: Path to the SQLite database
        query: SQL query to execute

    Returns:
        Tuple of (column_names, rows)

    Raises:
        DatabaseGenerationError: If query execution fails
    """
    if not os.path.exists(db_path):
        raise DatabaseGenerationError(f"Database file not found: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(query)
        results = cursor.fetchall()

        # Get column names
        column_names = [description[0] for description in cursor.description] if cursor.description else []

        conn.close()

        return column_names, results

    except sqlite3.Error as e:
        raise DatabaseGenerationError(f"Query execution failed: {str(e)}")


def delete_question_database(db_filename: str) -> None:
    """
    Delete a question database file.

    Args:
        db_filename: The database filename to delete
    """
    db_path = get_question_db_path(db_filename)

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception as e:
            # Log the error but don't raise
            print(f"Warning: Failed to delete database file {db_path}: {str(e)}")
