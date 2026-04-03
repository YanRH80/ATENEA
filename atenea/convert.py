"""
atenea/convert.py — Step 1: PDF to Markdown Conversion

Converts PDF files to markdown text using the Marker library.
This is the first step in the Atenea pipeline.

Pipeline position:
    [PDF file] → convert.py → raw_output.md → [chunk.py]

Functions:
    validate_pdf     — Check that the file exists and is a valid PDF
    get_marker_config — Build Marker configuration options
    convert_pdf_to_markdown — Main conversion function
"""

import shutil
from pathlib import Path

from rich.console import Console
from rich.progress import Progress

from atenea import storage
from atenea.utils import generate_id

console = Console()


def postprocess_ocr(text):
    """Clean common OCR artifacts from Marker output.

    Fixes UTF-8 encoding errors (mojibake), common character substitutions,
    and removes control characters that break downstream processing.

    Args:
        text: Raw markdown text from Marker.

    Returns:
        str — cleaned text.
    """
    import re as _re
    import unicodedata

    # Try to fix mojibake by re-encoding: if the text looks like UTF-8
    # that was incorrectly decoded as Latin-1, reverse the damage.
    # This is the most robust approach rather than maintaining a static map.
    def _fix_mojibake(t):
        """Attempt to fix UTF-8 text that was decoded as Latin-1."""
        try:
            # If re-encoding as Latin-1 then decoding as UTF-8 produces valid text,
            # it was likely mojibake
            fixed = t.encode("latin-1").decode("utf-8")
            return fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            return t

    # Apply mojibake fix line by line to avoid corrupting good text
    fixed_lines = []
    for line in text.split("\n"):
        # Only attempt fix if line contains typical mojibake indicators
        if any(c in line for c in ("Ã", "Â", "â€")):
            fixed_lines.append(_fix_mojibake(line))
        else:
            fixed_lines.append(line)
    text = "\n".join(fixed_lines)

    # Remove remaining non-printable control characters (except newlines/tabs)
    text = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Normalize unicode (NFC: composed form)
    text = unicodedata.normalize("NFC", text)

    # Fix common OCR character confusions
    # These are context-free single-char fixes safe for Spanish/English academic text
    ocr_fixes = {
        "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
        "\u200b": "",   # zero-width space
        "\u00a0": " ",  # non-breaking space → regular space
        "\ufeff": "",   # BOM
    }
    for bad, good in ocr_fixes.items():
        text = text.replace(bad, good)

    # Collapse multiple blank lines into max 2
    text = _re.sub(r'\n{4,}', '\n\n\n', text)

    return text


def validate_pdf(pdf_path):
    """Validate that a file exists and is a valid PDF.

    Checks:
    1. File exists on disk
    2. File has .pdf extension
    3. File starts with the PDF magic number (%PDF)

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        tuple (bool, str) — (is_valid, error_message_or_empty_string).
    """
    path = Path(pdf_path)

    if not path.exists():
        return False, f"File not found: {pdf_path}"

    if not path.is_file():
        return False, f"Not a file: {pdf_path}"

    if path.suffix.lower() != ".pdf":
        return False, f"Not a PDF file (extension: {path.suffix}): {pdf_path}"

    # Check PDF magic number
    try:
        with open(path, "rb") as f:
            header = f.read(5)
        if not header.startswith(b"%PDF"):
            return False, f"Invalid PDF (bad magic number): {pdf_path}"
    except OSError as e:
        return False, f"Cannot read file: {e}"

    return True, ""


def get_marker_config(use_llm=False):
    """Build configuration options for Marker's PdfConverter.

    Args:
        use_llm: If True, enable Marker's LLM-assisted mode for
            better handling of complex layouts, tables, and figures.

    Returns:
        dict — CLI-style options for marker.config.parser.ConfigParser.
    """
    config_options = {
        "output_format": "markdown",
    }

    if use_llm:
        config_options["use_llm"] = True

    return config_options


def convert_pdf_to_markdown(pdf_path, project_name, use_llm=False):
    """Convert a PDF file to markdown and save it in the project.

    This is the main function for Step 1 of the Atenea pipeline.
    It:
    1. Validates the PDF file
    2. Creates a new source directory in the project
    3. Copies the original PDF to the source directory
    4. Runs Marker to convert PDF → markdown
    5. Saves the markdown as raw_output.md
    6. Creates source-meta.json with metadata

    Args:
        pdf_path: Path to the input PDF file.
        project_name: Name of the Atenea project.
        use_llm: If True, use Marker's LLM-assisted mode.

    Returns:
        str — path to the saved raw_output.md file.

    Raises:
        ValueError: If the PDF is invalid.
        RuntimeError: If conversion fails.
    """
    # Validate PDF
    is_valid, error = validate_pdf(pdf_path)
    if not is_valid:
        raise ValueError(error)

    pdf_path = Path(pdf_path)

    # Create project and source directories
    storage.ensure_project_dir(project_name)
    source_id = storage.next_source_id(project_name)
    storage.ensure_source_dir(project_name, source_id)

    # Copy original PDF to source directory
    dest_pdf = storage.get_source_path(project_name, source_id, "original.pdf")
    shutil.copy2(pdf_path, dest_pdf)
    console.print(f"  Source: [bold]{source_id}[/bold] ← {pdf_path.name}")

    # Run Marker conversion
    console.print("  Loading Marker models...")
    with Progress(console=console, transient=True) as progress:
        task = progress.add_task("Converting PDF...", total=None)

        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict

            config_options = get_marker_config(use_llm)
            artifact_dict = create_model_dict()
            converter = PdfConverter(artifact_dict=artifact_dict, config=config_options)

            rendered = converter(str(pdf_path))
            progress.update(task, completed=True)
        except Exception as e:
            raise RuntimeError(f"Marker conversion failed: {e}") from e

    # Extract markdown text from rendered output
    # Marker returns a RenderedOutput with .markdown, .metadata, .images
    if hasattr(rendered, "markdown"):
        markdown_text = rendered.markdown
    elif hasattr(rendered, "text"):
        markdown_text = rendered.text
    elif isinstance(rendered, str):
        markdown_text = rendered
    else:
        # Try to get string representation
        markdown_text = str(rendered)

    if not markdown_text or not markdown_text.strip():
        raise RuntimeError("Marker produced empty output — check your PDF")

    # Post-process OCR artifacts
    markdown_text = postprocess_ocr(markdown_text)

    # Save markdown
    md_path = storage.get_source_path(project_name, source_id, "raw_output.md")
    storage.save_text(markdown_text, md_path)

    # Save source metadata
    meta = {
        "source_id": source_id,
        "filename": pdf_path.name,
        "title": pdf_path.stem,  # Will be refined by chunk.py or advisor
        "added_at": storage.now_iso(),
        "page_count": getattr(converter, "page_count", None),
        "use_llm": use_llm,
        "status": "converted",
        "markdown_length": len(markdown_text),
    }
    meta_path = storage.get_source_path(project_name, source_id, "source-meta.json")
    storage.save_json(meta, meta_path)

    # Update project.json
    _update_project_manifest(project_name, meta)

    console.print(f"  Markdown: {len(markdown_text):,} characters, "
                  f"{markdown_text.count(chr(10)):,} lines")

    return str(md_path)


def _update_project_manifest(project_name, source_meta):
    """Add a source entry to the project manifest (project.json).

    Creates project.json if it doesn't exist.

    Args:
        project_name: Name of the project.
        source_meta: Dict with source metadata.
    """
    manifest_path = storage.get_project_path(project_name, "project.json")
    manifest = storage.load_json(manifest_path)

    if not manifest:
        manifest = {
            "project_id": generate_id("proj"),
            "name": project_name,
            "created_at": storage.now_iso(),
            "sources": [],
            "settings": {},
        }

    manifest["updated_at"] = storage.now_iso()

    # Add source to manifest
    manifest.setdefault("sources", []).append({
        "source_id": source_meta["source_id"],
        "filename": source_meta["filename"],
        "title": source_meta["title"],
        "added_at": source_meta["added_at"],
        "status": source_meta["status"],
    })

    storage.save_json(manifest, manifest_path)
