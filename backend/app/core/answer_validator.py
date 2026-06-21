import hashlib
import json
from typing import List, Dict, Any, Tuple


def _normalize_value(value: Any) -> Any:
    """Normalize one cell value for hashing. Recurses into graph node/relationship dicts
    and lists so numeric properties inside them are coerced the same way scalar columns
    are -- otherwise `RETURN n` answers differ on int 25 vs float 25.0 inside the node."""
    if value is None:
        return None
    if isinstance(value, bool):
        # bool is an int subclass; keep it distinct from 0/1 so True does not hash as 1.
        return value
    if isinstance(value, (int, float)):
        # Convert all numbers to float for consistent type and hashing
        return float(value)
    if isinstance(value, bytes):
        return value.decode('utf-8')
    if isinstance(value, dict):
        return {k: _normalize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_value(v) for v in value]
    # Convert to string and normalize whitespace (multiple spaces -> single space)
    return ' '.join(str(value).strip().split())


def normalize_results(results: List[Tuple], columns: List[str]) -> List[Dict[str, Any]]:
    """
    Normalize query results for consistent comparison.

    Args:
        results: Raw query results as list of tuples
        columns: Column names

    Returns:
        Normalized results as list of dictionaries
    """
    result_dicts = [
        {col_name: _normalize_value(row[i]) for i, col_name in enumerate(columns)}
        for row in results
    ]

    # Sort results for consistent ordering regardless of the DB's physical row order.
    sorted_results = sorted(
        result_dicts,
        key=lambda x: json.dumps(x, sort_keys=True, default=str)
    )

    return sorted_results


def generate_hash(results: List[Tuple], columns: List[str]) -> str:
    """
    Generate SHA256 hash of normalized query results.

    Args:
        results: Raw query results as list of tuples
        columns: Column names

    Returns:
        SHA256 hash string
    """
    # Normalize results
    normalized = normalize_results(results, columns)

    # Convert to JSON string with sorted keys
    json_str = json.dumps(normalized, sort_keys=True, default=str)

    # Generate hash
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))
    return hash_obj.hexdigest()


def hash_run_result(result: Dict[str, Any]) -> str:
    """Hash a lab_query_executor result dict the same way authoring does: tuple-ize each row
    in column order, then generate_hash (which normalizes values). Shared by every SQL-lab
    grading path so in-lab and standalone solving can never diverge."""
    tuples = [tuple(row[col] for col in result["columns"]) for row in result["results"]]
    return generate_hash(tuples, result["columns"])


def validate_answer(
    user_results: List[Tuple],
    user_columns: List[str],
    correct_hash: str
) -> bool:
    """
    Validate user query results against correct answer hash.

    Args:
        user_results: User's query results
        user_columns: Column names from user's query
        correct_hash: Expected hash of correct answer

    Returns:
        True if answer is correct, False otherwise
    """
    user_hash = generate_hash(user_results, user_columns)
    return user_hash == correct_hash


def generate_hash_from_dict_list(results: List[Dict[str, Any]]) -> str:
    """
    Generate SHA256 hash from a list of dictionaries.
    Used when results are already in dictionary format.

    Args:
        results: Query results as list of dictionaries

    Returns:
        SHA256 hash string
    """
    # Sort results
    sorted_results = sorted(
        results,
        key=lambda x: json.dumps(x, sort_keys=True, default=str)
    )

    # Convert to JSON string with sorted keys
    json_str = json.dumps(sorted_results, sort_keys=True, default=str)

    # Generate hash
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))
    return hash_obj.hexdigest()
