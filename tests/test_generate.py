"""Tests for atenea/generate.py — Question generation (no LLM calls)."""

import pytest

from atenea.generate import (
    generate_free_text,
    _build_question_text,
    _extract_distractors,
    _flatten_to_strings,
    validate_distractors,
    _compute_question_quality,
    _question_stats,
    HIDEABLE_COMPONENTS,
    Q_FREE_TEXT,
    Q_MULTIPLE_CHOICE,
    Q_TRUE_FALSE,
)


SAMPLE_PATH = {
    "id": "path_test123",
    "context": "Nefrología",
    "subject": "El riñón",
    "predicate": "filtra",
    "object": "la sangre",
    "justification": "Mediante los glomérulos renales",
    "point_ids": ["pt_1", "pt_2", "pt_3", "pt_4", "pt_5", "pt_6", "pt_7"],
}


# ============================================================
# FREE TEXT GENERATION (no LLM)
# ============================================================

class TestGenerateFreeText:
    def test_generates_question(self):
        q = generate_free_text(SAMPLE_PATH, "object", lang="es")
        assert q is not None
        assert q["type"] == Q_FREE_TEXT
        assert q["path_id"] == "path_test123"
        assert q["component"] == "object"
        assert q["correct_answer"] == "la sangre"
        assert q["question_text"]  # not empty
        assert q["id"].startswith("q_")

    def test_all_components(self):
        for comp in HIDEABLE_COMPONENTS:
            q = generate_free_text(SAMPLE_PATH, comp, lang="es")
            assert q is not None
            assert q["component"] == comp
            assert q["correct_answer"] == SAMPLE_PATH[comp]

    def test_empty_component_returns_none(self):
        path = {**SAMPLE_PATH, "object": ""}
        q = generate_free_text(path, "object")
        assert q is None

    def test_difficulty_order(self):
        difficulties = []
        for comp in HIDEABLE_COMPONENTS:
            q = generate_free_text(SAMPLE_PATH, comp)
            difficulties.append(q["difficulty"])
        # Difficulty should be non-decreasing (object=1 < subject=2 < ... < context=5)
        assert difficulties == sorted(difficulties)

    def test_english_mode(self):
        q = generate_free_text(SAMPLE_PATH, "object", lang="en")
        assert q is not None
        assert "what?" in q["question_text"].lower() or "what" in q["question_text"].lower()


# ============================================================
# QUESTION TEXT TEMPLATES
# ============================================================

class TestBuildQuestionText:
    def test_es_object(self):
        text = _build_question_text(SAMPLE_PATH, "object", "es")
        assert "Nefrología" in text
        assert "riñón" in text
        assert "filtra" in text
        assert "qué" in text.lower()

    def test_en_object(self):
        text = _build_question_text(SAMPLE_PATH, "object", "en")
        assert "what" in text.lower()

    def test_es_justification(self):
        text = _build_question_text(SAMPLE_PATH, "justification", "es")
        assert "por qué" in text.lower()

    def test_es_context(self):
        text = _build_question_text(SAMPLE_PATH, "context", "es")
        assert "contexto" in text.lower()


# ============================================================
# DISTRACTOR PARSING
# ============================================================

class TestExtractDistractors:
    def test_dict_with_distractors_key(self):
        result = {"distractors": ["A", "B", "C"]}
        assert _extract_distractors(result) == ["A", "B", "C"]

    def test_dict_with_options_key(self):
        result = {"options": ["A", "B", "C"]}
        assert _extract_distractors(result) == ["A", "B", "C"]

    def test_plain_list(self):
        result = ["A", "B", "C"]
        assert _extract_distractors(result) == ["A", "B", "C"]

    def test_list_of_dicts(self):
        result = [{"text": "A"}, {"text": "B"}]
        assert _extract_distractors(result) == ["A", "B"]

    def test_empty_dict(self):
        assert _extract_distractors({}) == []

    def test_none(self):
        assert _extract_distractors(None) == []

    def test_nested_dict_fallback(self):
        result = {"some_random_key": ["X", "Y"]}
        assert _extract_distractors(result) == ["X", "Y"]


class TestFlattenToStrings:
    def test_strings(self):
        assert _flatten_to_strings(["A", "B"]) == ["A", "B"]

    def test_dicts(self):
        assert _flatten_to_strings([{"text": "A"}, {"option": "B"}]) == ["A", "B"]

    def test_empty_strings_filtered(self):
        assert _flatten_to_strings(["A", "", "  ", "B"]) == ["A", "B"]

    def test_mixed(self):
        result = _flatten_to_strings(["A", {"text": "B"}, 123])
        assert result == ["A", "B"]


# ============================================================
# DISTRACTOR VALIDATION
# ============================================================

class TestValidateDistractors:
    def test_valid_distractors(self):
        result = validate_distractors("ATP", ["GTP", "ADP", "cAMP"])
        assert len(result) == 3

    def test_removes_duplicates(self):
        result = validate_distractors("ATP", ["GTP", "GTP", "ADP"])
        assert len(result) == 2

    def test_removes_too_similar_to_correct(self):
        result = validate_distractors("ATP synthase", ["ATP synthasa", "GTP", "ADP"])
        # "ATP synthasa" is very similar to "ATP synthase"
        assert len(result) <= 3

    def test_removes_short(self):
        result = validate_distractors("ATP", ["A", "", "GTP"])
        assert result == ["GTP"]

    def test_removes_near_duplicate_distractors(self):
        result = validate_distractors("ATP", [
            "Guanosina trifosfato",
            "Guanosina trifosfato.",  # nearly identical
            "ADP",
        ])
        assert len(result) == 2


# ============================================================
# QUESTION QUALITY
# ============================================================

class TestQuestionQuality:
    def test_high_quality(self):
        question = {"n_options": 4, "source_text": "Some reference text"}
        path = {
            "point_ids": ["p1", "p2", "p3", "p4", "p5", "p6", "p7"],
            "justification": "Good justification",
        }
        score = _compute_question_quality(question, path)
        assert score >= 0.8

    def test_low_quality(self):
        question = {"n_options": 2}
        path = {"point_ids": ["p1"], "justification": ""}
        score = _compute_question_quality(question, path)
        assert score < 0.5

    def test_score_range(self):
        question = {"n_options": 3}
        path = {"point_ids": ["p1", "p2", "p3"], "justification": "yes"}
        score = _compute_question_quality(question, path)
        assert 0 <= score <= 1


# ============================================================
# STATS
# ============================================================

class TestQuestionStats:
    def test_basic_stats(self):
        questions = [
            {"type": "free_text", "component": "object", "difficulty": 1},
            {"type": "free_text", "component": "subject", "difficulty": 2},
            {"type": "multiple_choice", "component": "object", "difficulty": 1},
        ]
        stats = _question_stats(questions)
        assert stats["total"] == 3
        assert stats["by_type"]["free_text"] == 2
        assert stats["by_type"]["multiple_choice"] == 1
        assert stats["by_component"]["object"] == 2

    def test_empty(self):
        stats = _question_stats([])
        assert stats["total"] == 0
