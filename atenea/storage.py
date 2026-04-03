"""
atenea/storage.py — JSON File I/O and Project Management

== What this module does ==

This module handles all file operations for Atenea. Every data artifact
(clean-md.json, data.json, preguntas.json, analisis.json) is a JSON file
stored inside a project directory. This module provides functions to:

1. Read and write JSON files with consistent encoding (UTF-8, indented)
2. Resolve file paths within a project directory
3. Create and list project directories
4. Read and write plain text files (for raw_output.md)

== How projects are organized ==

    data/                       ← DEFAULT_DATA_DIR (from config/defaults.py)
    └── my-project/             ← One directory per project
        ├── project.json        ← Project metadata
        ├── sources/            ← One subdirectory per PDF source
        │   └── src-001/
        │       ├── original.pdf
        │       ├── raw_output.md
        │       ├── clean-md.json
        │       └── source-meta.json
        ├── data.json           ← Unified CSPOJ knowledge
        ├── preguntas.json      ← Generated questions
        ├── analisis.json       ← Learning analytics
        └── advisor-log.json    ← Advisor history

== Why plain JSON files instead of a database? ==

For the MVP, JSON files are:
- Human-readable: open any file in an editor to inspect
- Git-friendly: diff changes between versions
- Simple: no database setup, no ORM, no migrations
- Sufficient: until a project has thousands of paths, JSON is fast enough

The architecture is designed so that replacing JSON with SQLite later
only requires changing THIS module — no other module touches the filesystem.

== Concepts for non-programmers ==

JSON (JavaScript Object Notation): A text format for storing structured
data. It looks like: {"key": "value", "list": [1, 2, 3]}. Every data
file in Atenea is a JSON file.

Path: The location of a file on disk. Example: "./data/my-project/data.json".
This module builds these paths so other modules don't need to know the
directory structure.
"""

import json
import os
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
