"""Tests for atenea/utils.py — Shared utilities."""

import pytest

from atenea.utils import (
    generate_id,
    validate_element_count,
    validate_json_schema,
    validate_cspoj,
    truncate_text,
)
from config import defaults


class TestGenerateId:
    def test_format(self):
        id_ = generate_id("pt")
        assert id_.startswith("pt_")
        assert len(id_) == 2 + 1 + 8  # prefix + underscore + 8 hex chars

    def test_uniqueness(self):
        ids = {generate_id("q") for _ in range(100)}
        assert len(ids) == 100

    def test_various_prefixes(self):
        for prefix in ("pt", "path", "set", "map", "q", "sec", "src", "sess"):
            id_ = generate_id(prefix)
            assert id_.startswith(f"{prefix}_")


class TestValidateElementCount:
    def test_valid_count(self):
        items = list(range(7))
        ok, msg = validate_element_count(items)
        assert ok
        assert msg == ""

    def test_too_few(self):
        items = list(range(3))
        ok, msg = validate_element_count(items, label="points")
        assert not ok
        assert "Too few" in msg
        assert "points" in msg

    def test_too_many(self):
        items = list(range(15))
        ok, msg = validate_element_count(items)
        assert not ok
        assert "Too many" in msg

    def test_exact_min(self):
        items = list(range(defaults.MIN_ELEMENTS))
        ok, _ = validate_element_count(items)
        assert ok

    def test_exact_max(self):
        items = list(range(defaults.MAX_ELEMENTS))
        ok, _ = validate_element_count(items)
        assert ok


class TestValidateJsonSchema:
    def test_valid(self):
        data = {"id": "abc", "score": 0.5, "items": [1, 2]}
        errors = validate_json_schema(data, [
            ("id", str),
            ("score", (int, float)),
            ("items", list),
        ])
        assert errors == []

    def test_missing_field(self):
        errors = validate_json_schema({}, [("name", str)])
        assert len(errors) == 1
        assert "Missing" in errors[0]

    def test_wrong_type(self):
        errors = validate_json_schema({"x": "not_a_number"}, [("x", int)])
        assert len(errors) == 1
        assert "expected int" in errors[0]

    def test_tuple_types(self):
        errors = validate_json_schema({"x": 1.5}, [("x", (int, float))])
        assert errors == []


class TestValidateCSPOJ:
    def test_valid_cspoj(self):
        cspoj = {
            "context": "Biology",
            "subject": "Mitochondria",
            "predicate": "produces",
            "object": "ATP",
            "justification": "Through oxidative phosphorylation",
        }
        assert validate_cspoj(cspoj) == []

    def test_missing_component(self):
        cspoj = {"context": "Bio", "subject": "Mito"}
        errors = validate_cspoj(cspoj)
        assert len(errors) == 3  # missing predicate, object, justification

    def test_wrong_type(self):
        cspoj = {
            "context": "Bio",
            "subject": "Mito",
            "predicate": 123,  # should be str
            "object": "ATP",
            "justification": "reason",
        }
        errors = validate_cspoj(cspoj)
        assert len(errors) == 1


class TestTruncateText:
    def test_short_text(self):
        assert truncate_text("hello", 200) == "hello"

    def test_exact_length(self):
        text = "x" * 200
        assert truncate_text(text, 200) == text

    def test_truncated(self):
        text = "x" * 300
        result = truncate_text(text, 200)
        assert len(result) == 200
        assert result.endswith("...")

    def test_empty(self):
        assert truncate_text("", 10) == ""
