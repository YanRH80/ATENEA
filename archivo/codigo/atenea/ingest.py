"""
atenea/ingest.py — PDF Extraction (text, tables, images)

Extracts everything from a PDF into structured JSON:
- Text by page (pdfplumber)
- Tables with captions (pdfplumber)
- Images with surrounding text/captions (PyMuPDF/fitz)

Pipeline: PDF → text.json + tables.json + images/
"""

import os
import logging

import fitz  # PyMuPDF
import pdfplumber

from atenea import storage
from atenea.utils import generate_id

log = logging.getLogger(__name__)


# ============================================================
# TEXT EXTRACTION
# ============================================================

def extract_text(pdf_path):
    """Extract text from each page of a PDF.

    Returns:
        list[dict]: [{"page": 1, "text": "..."}, ...]
    """
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            text = _clean_text(text.strip())
            if text:
                pages.append({"page": i, "text": text})
    log.info(f"Extracted text from {len(pages)} pages")
    return pages


def _clean_text(text):
    """Clean PDF extraction artifacts.

    Fixes:
    - (cid:XXX) character codes from PDF fonts
    - Multiple spaces/newlines
    - Common mojibake
    """
    import re
    # Remove (cid:XXX) codes — these are font-specific, not Unicode.
    # Map known ones from medical PDFs; remove unknown ones silently.
    cid_map = {
        20: ";", 40: "(", 41: ")", 126: "≤",
        341: "ú",
    }
    def replace_cid(match):
        code = int(match.group(1))
        return cid_map.get(code, "")

    text = re.sub(r"\(cid:(\d+)\)", replace_cid, text)
    # Collapse multiple spaces
    text = re.sub(r" {2,}", " ", text)
    # Collapse multiple blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ============================================================
# TABLE EXTRACTION
# ============================================================

def extract_tables(pdf_path):
    """Extract tables from PDF with captions.

    Detects caption by looking at text immediately before the table
    on the same page (lines containing 'tabla', 'table', 'cuadro').

    Returns:
        list[dict]: [{"page": 3, "caption": "...", "headers": [...], "rows": [[...]]}]
    """
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            page_tables = page.extract_tables()
            if not page_tables:
                continue

            page_text = page.extract_text() or ""

            for raw_table in page_tables:
                if not raw_table or len(raw_table) < 2:
                    continue

                # First row as headers, rest as data
                headers = [str(c or "").strip() for c in raw_table[0]]
                rows = []
                for row in raw_table[1:]:
                    rows.append([str(c or "").strip() for c in row])

                # Try to find caption in page text
                caption = _clean_text(_find_caption(page_text))
                headers = [_clean_text(h) for h in headers]
                rows = [[_clean_text(c) for c in row] for row in rows]

                tables.append({
                    "id": generate_id("tbl"),
                    "page": i,
                    "caption": caption,
                    "headers": headers,
                    "rows": rows,
                })

    log.info(f"Extracted {len(tables)} tables")
    return tables


def _find_caption(page_text):
    """Find table/figure caption in page text."""
    for line in page_text.split("\n"):
        line_lower = line.strip().lower()
        for keyword in ["tabla", "table", "cuadro"]:
            if line_lower.startswith(keyword):
                return line.strip()
    return ""


# ============================================================
# IMAGE EXTRACTION
# ============================================================

def extract_images(pdf_path, output_dir):
    """Extract images from PDF using PyMuPDF.

    Saves each image as PNG. Tries to find caption text near the image.

    Returns:
        list[dict]: [{"page": 5, "path": "img-001.png", "caption": "..."}]
    """
    os.makedirs(output_dir, exist_ok=True)
    images = []
    doc = fitz.open(pdf_path)

    img_count = 0
    for page_num in range(len(doc)):
        page = doc[page_num]
        image_list = page.get_images(full=True)

        for img_info in image_list:
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
            except Exception:
                continue

            if not base_image or not base_image.get("image"):
                continue

            # Skip tiny images (likely icons/bullets)
            if base_image.get("width", 0) < 50 or base_image.get("height", 0) < 50:
                continue

            img_count += 1
            ext = base_image.get("ext", "png")
            filename = f"img-{img_count:03d}.{ext}"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "wb") as f:
                f.write(base_image["image"])

            # Try to find caption from page text
            page_text = page.get_text() or ""
            caption = _find_figure_caption(page_text)

            images.append({
                "id": generate_id("img"),
                "page": page_num + 1,
                "path": filename,
                "caption": caption,
                "width": base_image.get("width", 0),
                "height": base_image.get("height", 0),
            })

    doc.close()
    log.info(f"Extracted {len(images)} images")
    return images


def _find_figure_caption(page_text):
    """Find figure caption in page text."""
    for line in page_text.split("\n"):
        line_lower = line.strip().lower()
        for keyword in ["figura", "figure", "fig.", "fig "]:
            if line_lower.startswith(keyword):
                return line.strip()
    return ""


# ============================================================
# ORCHESTRATOR
# ============================================================

def ingest_pdf(pdf_path, project_name):
    """Extract everything from a PDF and save to project.

    Creates:
        sources/src-XXX/text.json     — text by page
        sources/src-XXX/tables.json   — extracted tables
        sources/src-XXX/images/       — extracted images
        sources/src-XXX/original.pdf  — copy of original

    Returns:
        dict with stats: {source_id, pages, tables, images}
    """
    import shutil

    # Setup project and source dirs
    source_id = storage.next_source_id(project_name)
    source_dir = storage.ensure_source_dir(project_name, source_id)
    images_dir = os.path.join(source_dir, "images")

    # Copy original PDF
    dest_pdf = os.path.join(source_dir, "original.pdf")
    shutil.copy2(pdf_path, dest_pdf)

    # Extract everything
    text_pages = extract_text(pdf_path)
    tables = extract_tables(pdf_path)
    images = extract_images(pdf_path, images_dir)

    # Save JSON
    text_path = storage.get_source_path(project_name, source_id, "text.json")
    tables_path = storage.get_source_path(project_name, source_id, "tables.json")

    storage.save_json({"pages": text_pages}, str(text_path))
    storage.save_json({"tables": tables}, str(tables_path))

    # Save source metadata
    meta = {
        "source_id": source_id,
        "filename": os.path.basename(pdf_path),
        "citekey": _make_citekey(os.path.basename(pdf_path)),
        "created": storage.now_iso(),
        "stats": {
            "pages": len(text_pages),
            "tables": len(tables),
            "images": len(images),
            "total_chars": sum(len(p["text"]) for p in text_pages),
        },
    }
    meta_path = storage.get_source_path(project_name, source_id, "source-meta.json")
    storage.save_json(meta, str(meta_path))

    # Update project manifest
    project_path = storage.get_project_path(project_name, "project.json")
    project_data = storage.load_json(str(project_path)) or {
        "name": project_name,
        "created": storage.now_iso(),
        "sources": [],
    }
    project_data["sources"].append({
        "source_id": source_id,
        "filename": meta["filename"],
        "citekey": meta["citekey"],
        "added": storage.now_iso(),
    })
    storage.save_json(project_data, str(project_path))

    return {
        "source_id": source_id,
        "pages": len(text_pages),
        "tables": len(tables),
        "images": len(images),
        "total_chars": meta["stats"]["total_chars"],
    }


def _make_citekey(filename):
    """Generate a simple citekey from filename.

    '44. 12 Octubre.pdf' → '12octubre'
    'Harrison-Nefrologia.pdf' → 'harrison-nefrologia'
    """
    name = os.path.splitext(filename)[0]
    # Remove leading numbers and dots
    import re
    name = re.sub(r"^\d+\.\s*", "", name)
    # Lowercase, replace spaces with hyphens
    name = name.lower().strip().replace(" ", "-")
    # Remove special chars
    name = re.sub(r"[^a-z0-9\-]", "", name)
    return name
