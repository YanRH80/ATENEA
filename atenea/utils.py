"""
atenea/utils.py — Shared Utilities

Pure utility functions used across modules: ID generation, validation,
formatting. No side effects, no I/O, no AI calls.
"""

import uuid

from config import defaults


def generate_id(prefix):
    """Generate a unique ID with a human-readable prefix.

    Format: "{prefix}_{8-char-hex}"
    Example: generate_id("pt") → "pt_a1b2c3d4"

    Args:
        prefix: Short string prefix (e.g., "pt", "path", "set", "map", "q", "sec", "src").

    Returns:
        str — unique ID.
    """
    short_uuid = uuid.uuid4().hex[:8]
    return f"{prefix}_{short_uuid}"


def validate_element_count(items, label="items"):
    """Check that a list has between MIN_ELEMENTS and MAX_ELEMENTS items.

    Implements the 7±2 rule (Miller, 1956). Used to validate that:
    - A path references 5-9 points
    - A map contains 5-9 paths

    Args:
        items: List to validate.
        label: Human-readable name for error messages (e.g., "points in path").

    Returns:
        tuple (bool, str) — (is_valid, error_message_or_empty_string).
    """
    count = len(items)
    if count < defaults.MIN_ELEMENTS:
        return False, f"Too few {label}: {count} (minimum {defaults.MIN_ELEMENTS})"
    if count > defaults.MAX_ELEMENTS:
        return False, f"Too many {label}: {count} (maximum {defaults.MAX_ELEMENTS})"
    return True, ""


def validate_json_schema(data, required_fields):
    """Validate that a dict contains required fields with expected types.

    Simple schema validation without external dependencies. Checks
    field presence and type. Does NOT validate nested structures.

    Args:
        data: Dict to validate.
        required_fields: List of tuples (field_name, expected_type).
            Example: [("id", str), ("score", (int, float)), ("items", list)]

    Returns:
        list[str] — list of error messages (empty if valid).
    """
    errors = []
    for field_name, expected_type in required_fields:
        if field_name not in data:
            errors.append(f"Missing required field: '{field_name}'")
        elif not isinstance(data[field_name], expected_type):
            actual = type(data[field_name]).__name__
            if isinstance(expected_type, tuple):
                expected = " or ".join(t.__name__ for t in expected_type)
            else:
                expected = expected_type.__name__
            errors.append(
                f"Field '{field_name}': expected {expected}, got {actual}"
            )
    return errors


def validate_cspoj(cspoj):
    """Validate that a dict has all required CSPOJ fields.

    Args:
        cspoj: Dict to validate.

    Returns:
        list[str] — list of error messages (empty if valid).
    """
    return validate_json_schema(cspoj, [
        ("context", str),
        ("subject", str),
        ("predicate", str),
        ("object", str),
        ("justification", str),
    ])


def truncate_text(text, max_length=200):
    """Truncate text to a maximum length, adding ellipsis if needed.

    Args:
        text: String to truncate.
        max_length: Maximum character length.

    Returns:
        str — truncated text.
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
