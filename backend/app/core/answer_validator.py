import hashlib
import json
from typing import List, Dict, Any, Tuple


def normalize_results(
    results: List[Tuple],
    columns: List[str],
    order_sensitive: bool = False
) -> List[Dict[str, Any]]:
    """
    Normalize query results for consistent comparison.

    Args:
        results: Raw query results as list of tuples
        columns: Column names
        order_sensitive: When True, preserve row order (do not sort rows).
            Used for questions that require results in a specific order
            (e.g. an explicit ORDER BY). Column order is always normalized.

    Returns:
        Normalized results as list of dictionaries
    """
    # Convert tuples to dictionaries
    result_dicts = []
    for row in results:
        row_dict = {}
        for i, col_name in enumerate(columns):
            value = row[i]

            # Normalize value
            if value is None:
                row_dict[col_name] = None
            elif isinstance(value, (int, float)):
                # Convert all numbers to float for consistent type and hashing
                row_dict[col_name] = float(value)
            elif isinstance(value, bytes):
                # Convert bytes to string
                row_dict[col_name] = value.decode('utf-8')
            else:
                # Convert to string and normalize whitespace
                normalized = str(value).strip()
                # Normalize internal whitespace: multiple spaces → single space
                normalized = ' '.join(normalized.split())
                row_dict[col_name] = normalized

        result_dicts.append(row_dict)

    # When grading is order-sensitive, preserve the original row order so that
    # a different ordering produces a different hash.
    if order_sensitive:
        return result_dicts

    # Sort results by all columns for consistent ordering
    # Convert each dict to a sorted tuple of items for comparison
    sorted_results = sorted(
        result_dicts,
        key=lambda x: json.dumps(x, sort_keys=True, default=str)
    )

    return sorted_results


def generate_hash(
    results: List[Tuple],
    columns: List[str],
    order_sensitive: bool = False
) -> str:
    """
    Generate SHA256 hash of normalized query results.

    Args:
        results: Raw query results as list of tuples
        columns: Column names
        order_sensitive: When True, row order is preserved and affects the hash.

    Returns:
        SHA256 hash string
    """
    # Normalize results
    normalized = normalize_results(results, columns, order_sensitive=order_sensitive)

    # Convert to JSON string with sorted keys
    json_str = json.dumps(normalized, sort_keys=True, default=str)

    # Generate hash
    hash_obj = hashlib.sha256(json_str.encode('utf-8'))
    return hash_obj.hexdigest()


def validate_answer(
    user_results: List[Tuple],
    user_columns: List[str],
    correct_hash: str,
    order_sensitive: bool = False
) -> bool:
    """
    Validate user query results against correct answer hash.

    Args:
        user_results: User's query results
        user_columns: Column names from user's query
        correct_hash: Expected hash of correct answer
        order_sensitive: When True, the user's rows must be in the same order
            as the correct answer to match.

    Returns:
        True if answer is correct, False otherwise
    """
    user_hash = generate_hash(user_results, user_columns, order_sensitive=order_sensitive)
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
