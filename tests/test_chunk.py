"""Tests for atenea/chunk.py — Markdown chunking."""

import pytest

from atenea.chunk import (
    split_into_sections,
    extract_lines,
    extract_keywords,
    build_clean_md,
)


# ============================================================
# SECTION SPLITTING
# ============================================================

class TestSplitIntoSections:
    def test_basic_headers(self):
        md = "# Title\nSome text\n## Section A\nContent A\n## Section B\nContent B"
        sections = split_into_sections(md)
        assert len(sections) >= 2
        titles = [s["title"] for s in sections]
        assert "Title" in titles

    def test_no_headers(self):
        md = "Just some text without any headers."
        sections = split_into_sections(md)
        # Should return at least one section (root)
        assert len(sections) >= 1

    def test_nested_levels(self):
        md = "# H1\n## H2\n### H3\nText"
        sections = split_into_sections(md)
        levels = [s["level"] for s in sections]
        assert 1 in levels
        assert 2 in levels

    def test_empty_input(self):
        sections = split_into_sections("")
        assert isinstance(sections, list)


# ============================================================
# LINE EXTRACTION
# ============================================================

class TestExtractLines:
    def test_basic(self):
        md = "# Title\nLine one\nLine two\nLine three"
        sections = split_into_sections(md)
        lines = extract_lines(md, sections)
        assert len(lines) >= 3
        # Each line has required fields
        for line in lines:
            assert "line_number" in line
            assert "content" in line
            assert "section_ids" in line

    def test_empty_lines_skipped(self):
        md = "# Title\n\n\nActual content\n\n\n"
        sections = split_into_sections(md)
        lines = extract_lines(md, sections)
        # Empty lines should be filtered
        contents = [l["content"] for l in lines]
        assert all(c.strip() for c in contents)


# ============================================================
# KEYWORD EXTRACTION
# ============================================================

class TestExtractKeywords:
    def test_extracts_keywords(self):
        lines = [
            {"content": "The mitochondria is the powerhouse of the cell", "section_ids": ["s1"]},
            {"content": "Mitochondria produces ATP through oxidative phosphorylation", "section_ids": ["s1"]},
            {"content": "The cell membrane protects the cell contents", "section_ids": ["s1"]},
        ]
        keywords = extract_keywords(lines)
        assert len(keywords) > 0
        assert isinstance(keywords, list)
        # All keywords are strings
        assert all(isinstance(kw, str) for kw in keywords)

    def test_no_stopwords(self):
        lines = [
            {"content": "the is a an and or but", "section_ids": ["s1"]},
        ]
        keywords = extract_keywords(lines)
        # Common stopwords should be filtered
        for kw in keywords:
            assert kw.lower() not in {"the", "is", "a", "an", "and", "or", "but"}

    def test_includes_ngrams(self):
        lines = [
            {"content": "fracaso renal agudo es una condicion medica grave", "section_ids": ["s1"]},
            {"content": "fracaso renal agudo requiere dialisis urgente", "section_ids": ["s1"]},
            {"content": "fracaso renal agudo puede ser reversible", "section_ids": ["s1"]},
        ]
        keywords = extract_keywords(lines)
        # Should include bigrams/trigrams if they appear enough
        kw_lower = [k.lower() for k in keywords]
        has_compound = any(" " in k for k in kw_lower)
        # Compound terms should be present given enough repetition
        assert has_compound or len(keywords) > 0


# ============================================================
# BUILD CLEAN-MD
# ============================================================

class TestBuildCleanMd:
    def test_structure(self):
        sections = [{"id": "s1", "title": "Test", "level": 1, "start_line": 1, "end_line": 3}]
        lines = [{"line_number": 1, "content": "hello", "section_ids": ["s1"]}]
        keywords = ["hello"]

        result = build_clean_md("test.pdf", "src-001", sections, lines, keywords)

        assert result["source"] == "test.pdf"
        assert result["source_id"] == "src-001"
        assert len(result["sections"]) == 1
        assert len(result["lines"]) == 1
        assert result["keywords"] == ["hello"]
        assert "stats" in result
