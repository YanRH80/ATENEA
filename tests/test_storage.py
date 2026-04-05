"""
tests/test_storage.py — Storage layer tests.

Tests load/save JSON, text I/O, project/source path management,
bibliography envelope, source text loading.

All tests use the tmp_data_dir fixture from conftest.py so
real user data (~/.atenea/data/) is never touched.
"""

import json
import os

import pytest

from atenea import storage


# ============================================================
# JSON I/O
# ============================================================

class TestLoadJson:

    def test_loads_valid_json(self, tmp_path):
        p = tmp_path / "test.json"
        p.write_text('{"key": "value"}')
        assert storage.load_json(str(p)) == {"key": "value"}

    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert storage.load_json(str(tmp_path / "nope.json")) == {}

    def test_unicode_preserved(self, tmp_path):
        p = tmp_path / "utf8.json"
        p.write_text('{"name": "hipertensión arterial"}', encoding="utf-8")
        assert storage.load_json(str(p))["name"] == "hipertensión arterial"

    def test_nested_structure(self, tmp_path):
        data = {"a": {"b": [1, 2, {"c": True}]}}
        p = tmp_path / "nested.json"
        p.write_text(json.dumps(data))
        assert storage.load_json(str(p)) == data


class TestSaveJson:

    def test_roundtrip(self, tmp_path):
        data = {"items": [1, 2, 3], "meta": {"ok": True}}
        path = str(tmp_path / "out.json")
        storage.save_json(data, path)
        assert storage.load_json(path) == data

    def test_creates_parent_dirs(self, tmp_path):
        path = str(tmp_path / "a" / "b" / "c" / "data.json")
        storage.save_json({"x": 1}, path)
        assert storage.load_json(path) == {"x": 1}

    def test_unicode_roundtrip(self, tmp_path):
        data = {"texto": "señalización intracelular"}
        path = str(tmp_path / "utf8.json")
        storage.save_json(data, path)
        assert storage.load_json(path)["texto"] == "señalización intracelular"

    def test_returns_path(self, tmp_path):
        path = str(tmp_path / "ret.json")
        result = storage.save_json({}, path)
        assert result == path

    def test_overwrites_existing(self, tmp_path):
        path = str(tmp_path / "over.json")
        storage.save_json({"v": 1}, path)
        storage.save_json({"v": 2}, path)
        assert storage.load_json(path)["v"] == 2


# ============================================================
# TEXT I/O
# ============================================================

class TestTextIO:

    def test_load_text_roundtrip(self, tmp_path):
        path = str(tmp_path / "doc.md")
        storage.save_text("# Hello\nWorld", path)
        assert storage.load_text(path) == "# Hello\nWorld"

    def test_load_text_missing_returns_empty(self, tmp_path):
        assert storage.load_text(str(tmp_path / "nope.txt")) == ""

    def test_save_text_creates_dirs(self, tmp_path):
        path = str(tmp_path / "deep" / "dir" / "file.txt")
        storage.save_text("content", path)
        assert storage.load_text(path) == "content"

    def test_save_text_returns_path(self, tmp_path):
        path = str(tmp_path / "ret.txt")
        assert storage.save_text("x", path) == path


# ============================================================
# PROJECT PATHS
# ============================================================

class TestProjectPaths:

    def test_get_project_dir(self, tmp_data_dir):
        d = storage.get_project_dir("myproj")
        assert str(d).endswith("myproj")
        assert str(tmp_data_dir) in str(d)

    def test_get_project_path(self, tmp_data_dir):
        p = storage.get_project_path("myproj", "knowledge.json")
        assert str(p).endswith("myproj/knowledge.json")

    def test_get_source_dir(self, tmp_data_dir):
        d = storage.get_source_dir("myproj", "src-001")
        assert str(d).endswith("myproj/sources/src-001")

    def test_get_source_path(self, tmp_data_dir):
        p = storage.get_source_path("myproj", "src-001", "text.json")
        assert str(p).endswith("myproj/sources/src-001/text.json")


# ============================================================
# DIRECTORY MANAGEMENT
# ============================================================

class TestDirectoryManagement:

    def test_ensure_project_dir_creates_dirs(self, tmp_data_dir):
        storage.ensure_project_dir("newproj")
        d = storage.get_project_dir("newproj")
        assert d.is_dir()
        assert (d / "sources").is_dir()

    def test_ensure_project_dir_idempotent(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_project_dir("proj")  # should not error
        assert storage.get_project_dir("proj").is_dir()

    def test_ensure_source_dir_creates_dir(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_source_dir("proj", "src-001")
        assert storage.get_source_dir("proj", "src-001").is_dir()

    def test_ensure_project_dir_returns_path(self, tmp_data_dir):
        result = storage.ensure_project_dir("proj")
        assert "proj" in result


# ============================================================
# LIST PROJECTS / SOURCES
# ============================================================

class TestListOperations:

    def test_list_projects_empty(self, tmp_data_dir):
        assert storage.list_projects() == []

    def test_list_projects(self, tmp_data_dir):
        storage.ensure_project_dir("alpha")
        storage.ensure_project_dir("beta")
        result = storage.list_projects()
        assert result == ["alpha", "beta"]  # sorted

    def test_list_projects_ignores_dotfiles(self, tmp_data_dir):
        storage.ensure_project_dir("real")
        os.makedirs(os.path.join(tmp_data_dir, ".hidden"), exist_ok=True)
        assert storage.list_projects() == ["real"]

    def test_list_sources_empty(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        assert storage.list_sources("proj") == []

    def test_list_sources(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_source_dir("proj", "src-001")
        storage.ensure_source_dir("proj", "src-002")
        result = storage.list_sources("proj")
        assert result == ["src-001", "src-002"]

    def test_list_sources_ignores_dotfiles(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_source_dir("proj", "src-001")
        os.makedirs(str(storage.get_project_dir("proj") / "sources" / ".tmp"), exist_ok=True)
        assert storage.list_sources("proj") == ["src-001"]


# ============================================================
# NEXT SOURCE ID
# ============================================================

class TestNextSourceId:

    def test_first_source(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        assert storage.next_source_id("proj") == "src-001"

    def test_sequential(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_source_dir("proj", "src-001")
        storage.ensure_source_dir("proj", "src-002")
        assert storage.next_source_id("proj") == "src-003"

    def test_gaps_in_numbering(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_source_dir("proj", "src-001")
        storage.ensure_source_dir("proj", "src-005")
        assert storage.next_source_id("proj") == "src-006"


# ============================================================
# NOW ISO
# ============================================================

class TestNowIso:

    def test_returns_iso_format(self):
        result = storage.now_iso()
        assert "T" in result
        assert "+" in result or "Z" in result


# ============================================================
# BIBLIOGRAPHY ENVELOPE
# ============================================================

class TestBibliography:

    def test_save_and_load_roundtrip(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        entries = [{"citekey": "Smith2024", "title": "Test"}]
        storage.save_bibliography("proj", entries)
        result = storage.load_bibliography("proj")
        assert result == entries

    def test_envelope_has_version(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.save_bibliography("proj", [])
        raw = storage.load_json(str(storage.get_project_path("proj", "bibliography.json")))
        assert raw["version"] == storage.BIBLIOGRAPHY_SCHEMA_VERSION
        assert "updated" in raw
        assert "entries" in raw

    def test_load_legacy_list_format(self, tmp_data_dir):
        """Old format was a bare list. load_bibliography handles this."""
        storage.ensure_project_dir("proj")
        legacy = [{"citekey": "Old2020"}]
        path = str(storage.get_project_path("proj", "bibliography.json"))
        storage.save_json(legacy, path)  # save as bare list
        result = storage.load_bibliography("proj")
        assert result == legacy

    def test_load_empty_returns_empty_list(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        result = storage.load_bibliography("proj")
        assert result == []

    def test_load_empty_dict_returns_empty_list(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        path = str(storage.get_project_path("proj", "bibliography.json"))
        storage.save_json({}, path)
        result = storage.load_bibliography("proj")
        assert result == []


# ============================================================
# PROJECT EXISTS / DELETE
# ============================================================

class TestProjectLifecycle:

    def test_project_exists(self, tmp_data_dir):
        assert not storage.project_exists("proj")
        storage.ensure_project_dir("proj")
        assert storage.project_exists("proj")

    def test_delete_project(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.save_json({"x": 1}, str(storage.get_project_path("proj", "data.json")))
        assert storage.delete_project("proj") is True
        assert not storage.project_exists("proj")

    def test_delete_nonexistent(self, tmp_data_dir):
        assert storage.delete_project("nope") is False


# ============================================================
# LOAD SOURCE TEXT
# ============================================================

class TestLoadSourceText:

    def _setup_source_with_text(self, tmp_data_dir, project="proj", source="src-001"):
        storage.ensure_project_dir(project)
        storage.ensure_source_dir(project, source)
        pages = [
            {"page": 1, "text": "Primer parrafo."},
            {"page": 2, "text": "Segundo parrafo."},
        ]
        text_path = str(storage.get_source_path(project, source, "text.json"))
        storage.save_json({"pages": pages}, text_path)
        return project, source

    def test_returns_full_text(self, tmp_data_dir):
        proj, src = self._setup_source_with_text(tmp_data_dir)
        text = storage.load_source_text(proj, src)
        assert "Primer parrafo." in text
        assert "Segundo parrafo." in text

    def test_with_pages_returns_tuple(self, tmp_data_dir):
        proj, src = self._setup_source_with_text(tmp_data_dir)
        text, pages = storage.load_source_text(proj, src, with_pages=True)
        assert isinstance(text, str)
        assert isinstance(pages, list)
        assert len(pages) == 2
        assert pages[0]["page"] == 1

    def test_missing_text_returns_empty_string(self, tmp_data_dir):
        storage.ensure_project_dir("empty")
        storage.ensure_source_dir("empty", "src-001")
        result = storage.load_source_text("empty", "src-001")
        assert result == ""

    def test_missing_text_with_pages_raises(self, tmp_data_dir):
        storage.ensure_project_dir("empty")
        storage.ensure_source_dir("empty", "src-001")
        with pytest.raises(ValueError, match="No text.json"):
            storage.load_source_text("empty", "src-001", with_pages=True)

    def test_pages_concatenated_with_double_newline(self, tmp_data_dir):
        proj, src = self._setup_source_with_text(tmp_data_dir)
        text = storage.load_source_text(proj, src)
        assert text == "Primer parrafo.\n\nSegundo parrafo."
