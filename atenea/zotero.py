"""
atenea/zotero.py — Zotero Library Sync

Synchronizes PDFs and metadata from a Zotero collection into an ATENEA project.
Zotero is the single source of truth for raw documents.

Pipeline: Zotero Collection → download PDFs → bibliography.json + sources/
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from pyzotero import zotero

from atenea import storage
from atenea.utils import generate_id
from config import defaults

log = logging.getLogger(__name__)


# ============================================================
# CONNECTION
# ============================================================

def connect(library_id=None, api_key=None, library_type=None):
    """Connect to Zotero API.

    Reads from params or .env: ZOTERO_LIBRARY_ID, ZOTERO_API_KEY, ZOTERO_LIBRARY_TYPE.

    Returns:
        pyzotero.zotero.Zotero client
    """
    library_id = library_id or os.environ.get("ZOTERO_LIBRARY_ID")
    api_key = api_key or os.environ.get("ZOTERO_API_KEY")
    library_type = library_type or os.environ.get("ZOTERO_LIBRARY_TYPE", "user")

    if not library_id or not api_key:
        raise ValueError(
            "Missing Zotero credentials. Set ZOTERO_LIBRARY_ID and ZOTERO_API_KEY "
            "in your .env file."
        )

    client = zotero.Zotero(library_id, library_type, api_key)
    # Verify connection
    client.key_info()
    log.info(f"Connected to Zotero library {library_id} ({library_type})")
    return client


# ============================================================
# COLLECTION NAVIGATION
# ============================================================

def list_collections(client):
    """List all collections in the library.

    Returns:
        list[dict]: [{"key": "ABC123", "name": "Nefrologia", "parent": None, "num_items": 12}, ...]
    """
    raw = client.collections()
    collections = []
    for c in raw:
        data = c["data"]
        collections.append({
            "key": data["key"],
            "name": data["name"],
            "parent": data.get("parentCollection", None) or None,
            "num_items": c["meta"].get("numItems", 0),
        })
    # Sort: top-level first, then by name
    collections.sort(key=lambda c: (c["parent"] or "", c["name"]))
    return collections


def get_subcollections(collections, parent_key=None):
    """Filter collections by parent. None = top-level."""
    return [c for c in collections if c["parent"] == parent_key]


def find_collection_by_name(collections, name):
    """Find a collection by exact or partial name match (case-insensitive)."""
    name_lower = name.lower()
    # Exact match first
    for c in collections:
        if c["name"].lower() == name_lower:
            return c
    # Partial match
    for c in collections:
        if name_lower in c["name"].lower():
            return c
    return None


# ============================================================
# ITEM LISTING
# ============================================================

def list_collection_items(client, collection_key):
    """List all items in a collection that have PDF attachments.

    Returns:
        list[dict]: Items with metadata, each having 'attachment_key' if PDF exists.
    """
    raw_items = client.collection_items(collection_key)
    # Filter out attachments and notes locally (avoids pyzotero URL encoding issues)
    items = [i for i in raw_items if i["data"].get("itemType") not in ("attachment", "note")]
    result = []

    for item in items:
        data = item["data"]
        item_key = data["key"]

        # Check for PDF attachment
        children = client.children(item_key, itemType="attachment")
        pdf_attachment = None
        for child in children:
            child_data = child["data"]
            if child_data.get("contentType") == "application/pdf":
                pdf_attachment = child_data["key"]
                break

        entry = {
            "key": item_key,
            "title": data.get("title", "Untitled"),
            "creators": data.get("creators", []),
            "date": data.get("date", ""),
            "item_type": data.get("itemType", "document"),
            "abstract": data.get("abstractNote", ""),
            "doi": data.get("DOI", ""),
            "url": data.get("url", ""),
            "tags": [t["tag"] for t in data.get("tags", [])],
            "extra": data.get("extra", ""),
            "attachment_key": pdf_attachment,
            "has_pdf": pdf_attachment is not None,
        }
        result.append(entry)

    result.sort(key=lambda x: x["title"])
    return result


# ============================================================
# PDF DOWNLOAD
# ============================================================

def download_pdf(client, attachment_key, dest_path):
    """Download a PDF attachment from Zotero to a local path.

    Returns:
        Path: The destination path where the PDF was saved.
    """
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    content = client.file(attachment_key)
    with open(dest_path, "wb") as f:
        f.write(content)

    log.info(f"Downloaded PDF → {dest_path} ({len(content):,} bytes)")
    return dest_path


def download_pdfs_concurrent(client, items_with_dest, max_workers=4):
    """Download multiple PDFs concurrently.

    Args:
        items_with_dest: list of (attachment_key, dest_path) tuples

    Returns:
        list[dict]: [{"attachment_key": ..., "path": ..., "size": ..., "error": ...}]
    """
    results = []

    def _download_one(attachment_key, dest_path):
        try:
            path = download_pdf(client, attachment_key, dest_path)
            size = path.stat().st_size
            return {"attachment_key": attachment_key, "path": str(path), "size": size, "error": None}
        except Exception as e:
            return {"attachment_key": attachment_key, "path": str(dest_path), "size": 0, "error": str(e)}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_download_one, att_key, dest): (att_key, dest)
            for att_key, dest in items_with_dest
        }
        for future in as_completed(futures):
            results.append(future.result())

    return results


# ============================================================
# METADATA EXTRACTION → CSL-JSON + VANCOUVER CITATION
# ============================================================

def extract_metadata(item, source_id, existing_citekeys=None):
    """Convert a Zotero item dict to a CSL-JSON compatible bibliography entry.

    Also generates a pre-formatted Vancouver citation string, assigns
    a default evidence level based on item type, and generates a short_title.

    Args:
        item: dict from list_collection_items()
        source_id: the ATENEA source ID assigned to this item
        existing_citekeys: set of citekeys already in the project (for dedup)

    Returns:
        dict: CSL-JSON entry with extra fields (source_id, evidence_level, citation_formatted, short_title)
    """
    if existing_citekeys is None:
        existing_citekeys = set()

    creators = item.get("creators", [])
    authors = []
    for c in creators:
        if c.get("creatorType") in ("author", "editor"):
            authors.append({
                "family": c.get("lastName", ""),
                "given": c.get("firstName", ""),
            })

    # Parse year from date string
    date_str = item.get("date", "")
    year = _parse_year(date_str)

    # Generate citekey: first-author-year or date_filename
    citekey = _make_citekey(authors, year, item.get("title", ""))

    # Check for Better BibTeX citekey in extra field (overrides auto-generated)
    bbt_citekey = _extract_bbt_citekey(item.get("extra", ""))
    if bbt_citekey:
        citekey = bbt_citekey

    # Deduplicate citekey within project
    citekey = _deduplicate_citekey(citekey, existing_citekeys)
    existing_citekeys.add(citekey)

    # Evidence level: "E" if insufficient metadata, else from item type
    item_type = item.get("item_type", "document")
    if _has_sufficient_metadata(authors, year):
        evidence_level = defaults.ZOTERO_TYPE_TO_EVIDENCE.get(item_type, "4")
    else:
        evidence_level = "E"

    synced_at = datetime.now(timezone.utc).isoformat()

    entry = {
        "id": citekey,
        "type": _zotero_to_csl_type(item_type),
        "title": item.get("title", "Untitled"),
        "short_title": _generate_short_title(item.get("title", "")),
        "author": authors,
        "issued": {"date-parts": [[year]]} if year else {},
        "abstract": item.get("abstract", ""),
        "DOI": item.get("doi", ""),
        "URL": item.get("url", ""),
        "source_id": source_id,
        "zotero_key": item.get("key", ""),
        "evidence_level": evidence_level,
        "recommendation_grade": _evidence_to_grade(evidence_level),
        "citation_formatted": _format_vancouver(authors, item.get("title", ""), year, item_type, synced_at, citekey),
        "synced_at": synced_at,
    }
    return entry


def _parse_year(date_str):
    """Extract year from various date formats."""
    if not date_str:
        return None
    # Try common formats
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(date_str.strip()[:10], fmt).year
        except ValueError:
            continue
    # Try to extract 4-digit year from string
    import re
    match = re.search(r"\b(19|20)\d{2}\b", date_str)
    return int(match.group()) if match else None


def _make_citekey(authors, year, title):
    """Generate citekey: first-author-year or YYYY-MM-DD_title-slug."""
    import re
    if authors and authors[0].get("family"):
        surname = authors[0]["family"].lower()
        surname = re.sub(r"[^a-z]", "", surname)
        yr = str(year) if year else "nd"
        return f"{surname}{yr}"
    # Fallback for documents without authors (hospital manuals, etc.)
    today = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]", "-", title.lower()[:40]).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return f"{today}_{slug}"


def _extract_bbt_citekey(extra):
    """Extract Better BibTeX citekey from Zotero 'extra' field."""
    import re
    match = re.search(r"Citation Key:\s*(.+)", extra, re.IGNORECASE)
    return match.group(1).strip() if match else None


def _deduplicate_citekey(citekey, existing_keys):
    """Ensure citekey is unique within the project.

    If 'garcia2024' already exists, returns 'garcia2024a', then 'garcia2024b', etc.

    Args:
        citekey: proposed citekey string.
        existing_keys: set of citekeys already in use.

    Returns:
        str — unique citekey.
    """
    if citekey not in existing_keys:
        return citekey
    for suffix in "abcdefghijklmnopqrstuvwxyz":
        candidate = f"{citekey}{suffix}"
        if candidate not in existing_keys:
            return candidate
    # Extremely unlikely: 26+ collisions
    return f"{citekey}_{datetime.now().strftime('%H%M%S')}"


def _has_sufficient_metadata(authors, year):
    """Check if a document has enough metadata to assign an evidence level.

    Returns False if there are no authors AND no year — meaning the
    evidence level mapping from item type is unreliable.

    Args:
        authors: list of author dicts.
        year: parsed year (int or None).

    Returns:
        bool — True if metadata is sufficient.
    """
    has_authors = any(a.get("family") for a in authors) if authors else False
    return has_authors or year is not None


def _generate_short_title(title, max_len=35):
    """Generate a truncated title for display in tables.

    Removes leading chapter numbers (e.g., "44. "), truncates at word boundary.

    Args:
        title: full document title.
        max_len: maximum character length.

    Returns:
        str — short title.
    """
    import re
    if not title:
        return "Sin titulo"
    # Remove leading chapter/section numbers
    clean = re.sub(r"^\d+[\.\)]\s*", "", title)
    if len(clean) <= max_len:
        return clean
    # Truncate at word boundary
    truncated = clean[:max_len].rsplit(" ", 1)[0]
    return f"{truncated}..." if truncated else clean[:max_len]


def _format_vancouver(authors, title, year, item_type, synced_at=None, citekey=None):
    """Format a citation in Vancouver style.

    Example: Garcia A, Lopez B. Fracaso renal agudo. 2024.
    Fallback (no authors, no year): [2026-04-04] citekey

    Args:
        authors: list of author dicts.
        title: document title.
        year: publication year (int or None).
        item_type: Zotero item type string.
        synced_at: ISO timestamp of sync (for fallback citation).
        citekey: citekey string (for fallback citation).
    """
    # Authors: Surname Initials, ...
    author_parts = []
    for a in (authors or [])[:6]:  # Vancouver: list up to 6
        family = a.get("family", "")
        given = a.get("given", "")
        initials = "".join(w[0].upper() for w in given.split() if w)
        if family:
            author_parts.append(f"{family} {initials}".strip())

    # Fallback for documents with no authors and no year
    if not author_parts and year is None:
        date_part = synced_at[:10] if synced_at else "s.f."
        ref = citekey or "unknown"
        return f"[{date_part}] {ref}"

    authors_str = ", ".join(author_parts) if author_parts else "Unknown"
    if len(authors or []) > 6:
        authors_str += ", et al"

    year_str = str(year) if year else "s.f."

    # Basic Vancouver format
    return f"{authors_str}. {title}. {year_str}."


def _zotero_to_csl_type(zotero_type):
    """Map Zotero item types to CSL-JSON types."""
    mapping = {
        "journalArticle": "article-journal",
        "book": "book",
        "bookSection": "chapter",
        "conferencePaper": "paper-conference",
        "thesis": "thesis",
        "report": "report",
        "webpage": "webpage",
        "preprint": "article",
        "review": "review",
        "encyclopediaArticle": "entry-encyclopedia",
    }
    return mapping.get(zotero_type, "document")


def _evidence_to_grade(evidence_level):
    """Map evidence level to recommendation grade."""
    mapping = {
        "1++": "A", "1+": "A",
        "1-": "B",
        "2++": "B", "2+": "C",
        "2-": "C",
        "3": "D", "4": "D",
        "E": "E",
    }
    return mapping.get(evidence_level, "D")


# ============================================================
# SYNC ENGINE
# ============================================================

def sync(client, project, collection_key, on_progress=None):
    """Synchronize a Zotero collection with a local ATENEA project.

    Compares local bibliography.json with remote Zotero state.
    Downloads new PDFs, marks removed items, updates metadata.

    Args:
        client: pyzotero client
        project: project name
        collection_key: Zotero collection key
        on_progress: callback(step, total, message) for UI updates

    Returns:
        dict: SyncResult with counts and details
    """
    t0 = time.time()

    def progress(step, total, msg):
        if on_progress:
            on_progress(step, total, msg)
        log.info(f"[{step}/{total}] {msg}")

    # 1. Load local bibliography (handles legacy array and envelope format)
    local_bib = storage.load_bibliography(project)
    local_by_zotero_key = {e["zotero_key"]: e for e in local_bib if "zotero_key" in e}

    # 2. Fetch remote items
    progress(1, 5, "Fetching items from Zotero...")
    remote_items = list_collection_items(client, collection_key)
    remote_by_key = {item["key"]: item for item in remote_items}

    # 3. Diff: new, updated, removed
    remote_keys = set(remote_by_key.keys())
    local_keys = set(local_by_zotero_key.keys())

    new_keys = remote_keys - local_keys
    removed_keys = local_keys - remote_keys
    existing_keys = remote_keys & local_keys

    progress(2, 5, f"Found {len(new_keys)} new, {len(existing_keys)} existing, {len(removed_keys)} removed")

    # 4. Download new PDFs
    # Build set of existing citekeys for deduplication
    existing_citekeys = {e["id"] for e in local_bib if "id" in e}
    new_entries = []
    downloads = []

    for key in sorted(new_keys):
        item = remote_by_key[key]
        if not item["has_pdf"]:
            log.warning(f"Skipping '{item['title']}' — no PDF attachment")
            continue

        source_id = storage.next_source_id(project)
        source_dir = storage.ensure_source_dir(project, source_id)
        dest_pdf = os.path.join(source_dir, "original.pdf")
        downloads.append((item["attachment_key"], dest_pdf, item, source_id))

    if downloads:
        progress(3, 5, f"Downloading {len(downloads)} PDFs...")
        download_tasks = [(att_key, dest) for att_key, dest, _, _ in downloads]
        results = download_pdfs_concurrent(client, download_tasks)

        # Map results back
        result_map = {r["attachment_key"]: r for r in results}

        for att_key, dest, item, source_id in downloads:
            dl = result_map.get(att_key, {})
            if dl.get("error"):
                log.error(f"Failed to download '{item['title']}': {dl['error']}")
                continue

            entry = extract_metadata(item, source_id, existing_citekeys)
            new_entries.append(entry)

            # Save source metadata
            meta = {
                "source_id": source_id,
                "filename": f"{entry['id']}.pdf",
                "citekey": entry["id"],
                "zotero_key": item["key"],
                "created": datetime.now(timezone.utc).isoformat(),
                "stats": {"size_bytes": dl.get("size", 0)},
            }
            meta_path = storage.get_source_path(project, source_id, "source-meta.json")
            storage.save_json(meta, str(meta_path))
    else:
        progress(3, 5, "No new PDFs to download")

    # 5. Mark removed items
    removed_entries = []
    for key in removed_keys:
        entry = local_by_zotero_key[key]
        if not entry.get("removed"):
            entry["removed"] = True
            entry["removed_at"] = datetime.now(timezone.utc).isoformat()
            removed_entries.append(entry)

    # 6. Build updated bibliography
    progress(4, 5, "Updating bibliography.json...")
    updated_bib = []
    # Keep existing (update removed flags)
    for entry in local_bib:
        zk = entry.get("zotero_key", "")
        if zk in removed_keys and not entry.get("removed"):
            entry["removed"] = True
            entry["removed_at"] = datetime.now(timezone.utc).isoformat()
        updated_bib.append(entry)
    # Add new
    updated_bib.extend(new_entries)

    storage.save_bibliography(project, updated_bib)

    # 7. Update project manifest
    project_path = storage.get_project_path(project, "project.json")
    project_data = storage.load_json(str(project_path)) or {
        "name": project,
        "created": datetime.now(timezone.utc).isoformat(),
        "sources": [],
        "zotero_collection": collection_key,
    }
    project_data["schema_version"] = 1
    project_data["zotero_collection"] = collection_key
    project_data["last_sync"] = datetime.now(timezone.utc).isoformat()

    # Add new sources to manifest
    for entry in new_entries:
        project_data.setdefault("sources", []).append({
            "source_id": entry["source_id"],
            "citekey": entry["id"],
            "title": entry["title"],
            "added": datetime.now(timezone.utc).isoformat(),
        })
    storage.save_json(project_data, str(project_path))

    elapsed = time.time() - t0
    progress(5, 5, f"Sync complete in {elapsed:.1f}s")

    return {
        "new": len(new_entries),
        "existing": len(existing_keys),
        "removed": len(removed_entries),
        "skipped_no_pdf": len(new_keys) - len(downloads),
        "errors": sum(1 for d in (downloads or []) if not any(
            e["source_id"] == d[3] for e in new_entries
        )) if downloads else 0,
        "total_items": len(remote_items),
        "elapsed_seconds": round(elapsed, 2),
        "bibliography_path": bib_path,
    }


# ============================================================
# RESET
# ============================================================

def reset_project(project, hard=False):
    """Reset project data for development/testing.

    Without --hard: deletes generated outputs (knowledge, questions, sessions, coverage)
    With --hard: deletes EVERYTHING including sources and bibliography

    Returns:
        list[str]: paths deleted
    """
    import shutil

    project_dir = storage.get_project_path(project, ".")
    if not os.path.isdir(str(project_dir)):
        raise ValueError(f"Project '{project}' not found")

    deleted = []

    # Always delete generated outputs
    output_files = ["knowledge.json", "questions.json", "sessions.json", "coverage.json"]
    for f in output_files:
        path = storage.get_project_path(project, f)
        if os.path.exists(str(path)):
            os.remove(str(path))
            deleted.append(f)

    if hard:
        # Delete everything
        project_path = str(storage.get_project_path(project, "."))
        shutil.rmtree(project_path)
        deleted.append(f"[entire project directory]")

    return deleted
