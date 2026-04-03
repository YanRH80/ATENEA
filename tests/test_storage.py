"""Tests for atenea/storage.py — File I/O and project management."""

import json
import os
import pytest
from pathlib import Path

from atenea import storage


@pytest.fixture
def tmp_data_dir(tmp_path, monkeypatch):
    """Use a temporary directory for all storage operations."""
    import config.defaults as defaults_mod
    monkeypatch.setattr(defaults_mod, "DEFAULT_DATA_DIR", str(tmp_path))
    return tmp_path


class TestJsonIO:
    def test_save_and_load(self, tmp_path):
        fpath = tmp_path / "test.json"
        data = {"key": "value", "nums": [1, 2, 3]}
        storage.save_json(data, fpath)
        loaded = storage.load_json(fpath)
        assert loaded == data

    def test_load_missing_returns_empty(self, tmp_path):
        assert storage.load_json(tmp_path / "nonexistent.json") == {}

    def test_unicode_preserved(self, tmp_path):
        fpath = tmp_path / "unicode.json"
        data = {"text": "Nefrología: fracaso renal agudo"}
        storage.save_json(data, fpath)
        loaded = storage.load_json(fpath)
        assert loaded["text"] == "Nefrología: fracaso renal agudo"

    def test_creates_parent_dirs(self, tmp_path):
        fpath = tmp_path / "a" / "b" / "c" / "test.json"
        storage.save_json({"x": 1}, fpath)
        assert fpath.exists()


class TestTextIO:
    def test_save_and_load(self, tmp_path):
        fpath = tmp_path / "test.md"
        storage.save_text("# Hello\nworld", fpath)
        text = storage.load_text(fpath)
        assert text == "# Hello\nworld"

    def test_load_missing_returns_empty(self, tmp_path):
        assert storage.load_text(tmp_path / "missing.md") == ""


class TestProjectDirs:
    def test_ensure_project_dir(self, tmp_data_dir):
        storage.ensure_project_dir("test-proj")
        assert (tmp_data_dir / "test-proj").is_dir()
        assert (tmp_data_dir / "test-proj" / "sources").is_dir()

    def test_ensure_source_dir(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_source_dir("proj", "src-001")
        assert (tmp_data_dir / "proj" / "sources" / "src-001").is_dir()

    def test_get_project_path(self, tmp_data_dir):
        path = storage.get_project_path("myproj", "data.json")
        assert str(path).endswith("myproj/data.json")

    def test_get_source_path(self, tmp_data_dir):
        path = storage.get_source_path("myproj", "src-001", "clean-md.json")
        assert "sources/src-001/clean-md.json" in str(path)


class TestListProjects:
    def test_empty(self, tmp_data_dir):
        assert storage.list_projects() == []

    def test_lists_projects(self, tmp_data_dir):
        storage.ensure_project_dir("alpha")
        storage.ensure_project_dir("beta")
        projects = storage.list_projects()
        assert projects == ["alpha", "beta"]

    def test_ignores_hidden(self, tmp_data_dir):
        storage.ensure_project_dir("visible")
        (tmp_data_dir / ".hidden").mkdir()
        assert storage.list_projects() == ["visible"]


class TestListSources:
    def test_empty(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        assert storage.list_sources("proj") == []

    def test_lists_sources(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_source_dir("proj", "src-001")
        storage.ensure_source_dir("proj", "src-002")
        sources = storage.list_sources("proj")
        assert sources == ["src-001", "src-002"]


class TestNextSourceId:
    def test_first_source(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        assert storage.next_source_id("proj") == "src-001"

    def test_increments(self, tmp_data_dir):
        storage.ensure_project_dir("proj")
        storage.ensure_source_dir("proj", "src-001")
        storage.ensure_source_dir("proj", "src-002")
        assert storage.next_source_id("proj") == "src-003"


class TestNowIso:
    def test_format(self):
        ts = storage.now_iso()
        assert "T" in ts
        assert "+" in ts or "Z" in ts
