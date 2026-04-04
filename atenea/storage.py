"""
atenea/storage.py — JSON File I/O and Project Management

All file operations for Atenea. Every data artifact is a JSON file
stored inside a project directory.

Project structure:
    ~/.atenea/data/
    └── {project}/
        ├── project.json        ← Project metadata + source list
        ├── sources/
        │   └── src-001/
        │       ├── original.pdf
        │       ├── text.json       ← Extracted text by page
        │       ├── tables.json     ← Extracted tables
        │       ├── images/         ← Extracted figures
        │       └── source-meta.json
        ├── knowledge.json      ← Keywords, associations, sequences, sets, maps
        ├── questions.json      ← Generated MIR questions
        ├── sessions.json       ← Test session history
        └── coverage.json       ← Per-item SM-2 coverage data

Plain JSON files: human-readable, git-friendly, simple. If scale demands
it, only THIS module needs to change — no other module touches the filesystem.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from config import defaults


def load_json(path):
    """Read a JSON file and return its contents as a dict.

    If the file does not exist, returns an empty dict (not an error).
    This allows modules to call load_json() without checking file existence.

    Args:
        path: Absolute or relative path to the JSON file.

    Returns:
        dict with the file contents, or {} if file doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, path):
    """Write a dict to a JSON file with consistent formatting.

    Creates parent directories if they don't exist. Uses indent=2 for
    readability and ensure_ascii=False to preserve unicode characters
    (Spanish accents, etc.).

    Args:
        data: Dict to write.
        path: Absolute or relative path for the output file.

    Returns:
        str — the path where the file was saved.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return str(path)


def load_text(path):
    """Read a plain text file and return its contents.

    Used for reading raw_output.md (markdown from PDF conversion).

    Args:
        path: Path to the text file.

    Returns:
        str — file contents, or "" if file doesn't exist.
    """
    path = Path(path)
    if not path.exists():
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def save_text(content, path):
    """Write a string to a plain text file.

    Creates parent directories if they don't exist.

    Args:
        content: String to write.
        path: Path for the output file.

    Returns:
        str — the path where the file was saved.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return str(path)


def get_project_dir(project_name):
    """Get the root directory for a project.

    Args:
        project_name: Name of the project (used as directory name).

    Returns:
        Path object for the project directory.
    """
    return Path(defaults.DEFAULT_DATA_DIR) / project_name


def get_project_path(project_name, filename):
    """Build the full path for a file within a project.

    Example:
        get_project_path("bio101", "data.json")
        → Path("./data/bio101/data.json")

    Args:
        project_name: Name of the project.
        filename: Name of the file (e.g., "data.json", "clean-md.json").

    Returns:
        Path object for the file.
    """
    return get_project_dir(project_name) / filename


def get_source_dir(project_name, source_id):
    """Get the directory for a specific source within a project.

    Example:
        get_source_dir("bio101", "src-001")
        → Path("./data/bio101/sources/src-001")

    Args:
        project_name: Name of the project.
        source_id: ID of the source (e.g., "src-001").

    Returns:
        Path object for the source directory.
    """
    return get_project_dir(project_name) / "sources" / source_id


def get_source_path(project_name, source_id, filename):
    """Build the full path for a file within a source directory.

    Example:
        get_source_path("bio101", "src-001", "clean-md.json")
        → Path("./data/bio101/sources/src-001/clean-md.json")

    Args:
        project_name: Name of the project.
        source_id: ID of the source.
        filename: Name of the file.

    Returns:
        Path object for the file.
    """
    return get_source_dir(project_name, source_id) / filename


def ensure_project_dir(project_name):
    """Create the project directory structure if it doesn't exist.

    Creates:
        data/{project_name}/
        data/{project_name}/sources/

    Args:
        project_name: Name of the project.

    Returns:
        str — path to the project directory.
    """
    project_dir = get_project_dir(project_name)
    sources_dir = project_dir / "sources"
    project_dir.mkdir(parents=True, exist_ok=True)
    sources_dir.mkdir(parents=True, exist_ok=True)
    return str(project_dir)


def ensure_source_dir(project_name, source_id):
    """Create a source directory within a project.

    Args:
        project_name: Name of the project.
        source_id: ID of the source.

    Returns:
        str — path to the source directory.
    """
    source_dir = get_source_dir(project_name, source_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    return str(source_dir)


def list_projects():
    """List all project directories in the data directory.

    Returns:
        list[str] — sorted list of project names.
    """
    data_dir = Path(defaults.DEFAULT_DATA_DIR)
    if not data_dir.exists():
        return []
    return sorted([
        d.name for d in data_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])


def list_sources(project_name):
    """List all source directories within a project.

    Returns:
        list[str] — sorted list of source IDs.
    """
    sources_dir = get_project_dir(project_name) / "sources"
    if not sources_dir.exists():
        return []
    return sorted([
        d.name for d in sources_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    ])


def next_source_id(project_name):
    """Generate the next sequential source ID for a project.

    If the project has sources src-001, src-002, returns "src-003".
    If no sources exist, returns "src-001".

    Args:
        project_name: Name of the project.

    Returns:
        str — next source ID (e.g., "src-003").
    """
    existing = list_sources(project_name)
    if not existing:
        return "src-001"
    # Extract numeric parts and find max
    nums = []
    for sid in existing:
        parts = sid.split("-")
        if len(parts) == 2 and parts[1].isdigit():
            nums.append(int(parts[1]))
    next_num = max(nums) + 1 if nums else 1
    return f"src-{next_num:03d}"


def now_iso():
    """Return current UTC timestamp in ISO 8601 format.

    Returns:
        str — e.g., "2026-04-03T10:30:00+00:00"
    """
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# BIBLIOGRAPHY ENVELOPE (versioned schema)
# ============================================================

BIBLIOGRAPHY_SCHEMA_VERSION = 1


def load_bibliography(project_name):
    """Load bibliography entries from a project.

    Handles both legacy format (bare list) and envelope format
    ({"version": N, "entries": [...]}).

    Args:
        project_name: Name of the project.

    Returns:
        list[dict] — bibliography entries (always a list).
    """
    bib_path = get_project_path(project_name, "bibliography.json")
    raw = load_json(str(bib_path))
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return raw.get("entries", [])
    return []


def save_bibliography(project_name, entries):
    """Save bibliography entries in versioned envelope format.

    Writes: {"version": N, "entries": [...], "updated": "ISO timestamp"}

    Args:
        project_name: Name of the project.
        entries: List of bibliography entry dicts.

    Returns:
        str — path where file was saved.
    """
    bib_path = get_project_path(project_name, "bibliography.json")
    envelope = {
        "version": BIBLIOGRAPHY_SCHEMA_VERSION,
        "entries": entries,
        "updated": now_iso(),
    }
    return save_json(envelope, str(bib_path))


def project_exists(project_name):
    """Check if a project directory exists.

    Args:
        project_name: Name of the project.

    Returns:
        bool — True if the project directory exists.
    """
    return get_project_dir(project_name).is_dir()


def delete_project(project_name):
    """Delete an entire project directory and all its contents.

    Args:
        project_name: Name of the project to delete.

    Returns:
        bool — True if deleted, False if project didn't exist.
    """
    project_dir = get_project_dir(project_name)
    if not project_dir.is_dir():
        return False
    shutil.rmtree(str(project_dir))
    return True


# ============================================================
# SOURCE TEXT LOADING
# ============================================================

def load_source_text(project, source_id, with_pages=False):
    """Load extracted text for a source, with optional PDF fallback.

    Args:
        project: Project name
        source_id: Source identifier
        with_pages: If True, return (full_text, pages) tuple.
                    If False, return just the full text string.

    Returns:
        str: Concatenated text (if with_pages=False)
        tuple: (full_text, pages) where pages is list[dict] (if with_pages=True)

    Raises:
        ValueError: If with_pages=True and no text is available.
    """
    text_path = get_source_path(project, source_id, "text.json")
    text_data = load_json(str(text_path))

    if text_data and text_data.get("pages"):
        pages = text_data["pages"]
    else:
        # Try extracting from PDF
        pdf_path = get_source_path(project, source_id, "original.pdf")
        if pdf_path.exists():
            try:
                from atenea.ingest import extract_text
                pages = extract_text(str(pdf_path))
                save_json({"pages": pages}, str(text_path))
            except Exception:
                pages = []
        else:
            pages = []

    if not pages:
        if with_pages:
            raise ValueError(f"No text.json found for {project}/{source_id}")
        return ""

    full_text = "\n\n".join(p["text"] for p in pages if p.get("text"))

    if with_pages:
        return full_text, pages
    return full_text
