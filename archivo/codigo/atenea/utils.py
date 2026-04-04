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
    Example: generate_id("kw") → "kw_a1b2c3d4"

    Args:
        prefix: Short string prefix (kw, as, sq, st, mp, q, src, tbl, img).

    Returns:
        str — unique ID.
    """
    short_uuid = uuid.uuid4().hex[:8]
    return f"{prefix}_{short_uuid}"


def validate_element_count(items, label="items"):
    """Check that a list has between MIN_ELEMENTS and MAX_ELEMENTS items.

    Implements the 7+-2 rule (Miller, 1956). Used to validate that
    sequences have 5-9 nodes and maps contain 5-9 sequences.

    Args:
        items: List to validate.
        label: Human-readable name for error messages.

    Returns:
        tuple (bool, str) — (is_valid, error_message_or_empty_string).
    """
    count = len(items)
    if count < defaults.MIN_ELEMENTS:
        return False, f"Too few {label}: {count} (minimum {defaults.MIN_ELEMENTS})"
    if count > defaults.MAX_ELEMENTS:
        return False, f"Too many {label}: {count} (maximum {defaults.MAX_ELEMENTS})"
    return True, ""


def truncate_text(text, max_length=200):
    """Truncate text to a maximum length, adding ellipsis if needed."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
