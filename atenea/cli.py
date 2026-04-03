"""
atenea/cli.py — Command Line Interface

Usage:
    atenea convert <pdf> --project <name>     # PDF -> Markdown
    atenea chunk <project>                     # Markdown -> clean-md.json
    atenea pipeline <pdf> --project <name>     # convert + chunk
    atenea projects                             # List projects
    atenea info <project>                      # Show project info
    atenea init                                 # Initialize data directory
    atenea doctor                               # Check dependencies
"""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
@click.version_option(package_name="atenea")
def main():
    """Atenea — Adaptive learning from documents."""
    pass


# ============================================================
# Step 1: PDF -> Markdown
# ============================================================

@main.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option("--project", "-p", required=True, help="Project name")
@click.option("--use-llm/--no-llm", default=False,
              help="Use Marker's LLM-assisted mode for complex PDFs")
def convert(pdf_path, project, use_llm):
    """Convert a PDF to markdown text."""
    from atenea.convert import convert_pdf_to_markdown
    result = convert_pdf_to_markdown(pdf_path, project, use_llm=use_llm)
    console.print(f"[green]OK[/green] Markdown saved: {result}")


# ============================================================
# Step 2: Markdown -> clean-md.json
# ============================================================

@main.command()
@click.argument("project")
@click.option("--source", "-s", default=None,
              help="Source ID to chunk (default: latest)")
def chunk(project, source):
    """Chunk markdown into structured clean-md.json."""
    from atenea.chunk import chunk_markdown
    result = chunk_markdown(project, source_id=source)
    n_sections = len(result.get("sections", []))
    n_lines = len(result.get("lines", []))
    n_keywords = len(result.get("keywords", []))
    console.print(f"[green]OK[/green] {n_sections} sections, "
                  f"{n_lines} lines, {n_keywords} keywords")


# ============================================================
# Pipeline: convert + chunk
# ============================================================

@main.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option("--project", "-p", required=True, help="Project name")
@click.option("--use-llm/--no-llm", default=False,
              help="Use Marker's LLM-assisted mode")
def pipeline(pdf_path, project, use_llm):
    """Run convert + chunk pipeline."""
    console.print("[bold]Step 1:[/bold] Converting PDF...")
    from atenea.convert import convert_pdf_to_markdown
    convert_pdf_to_markdown(pdf_path, project, use_llm=use_llm)
    console.print("[green]OK[/green] Convert complete")

    console.print("[bold]Step 2:[/bold] Chunking markdown...")
    from atenea.chunk import chunk_markdown
    result = chunk_markdown(project)
    n = len(result.get("sections", []))
    console.print(f"[green]OK[/green] Chunk complete ({n} sections)")


# ============================================================
# Project Management
# ============================================================

@main.command()
def projects():
    """List all learning projects."""
    from atenea.storage import list_projects
    project_list = list_projects()
    if not project_list:
        console.print("[dim]No projects. Create one with:[/dim]")
        console.print("  atenea convert <pdf> --project <name>")
        return

    table = Table(title="Projects")
    table.add_column("Project", style="bold")
    table.add_column("Sources", justify="right")

    from atenea.storage import list_sources
    for p in project_list:
        sources = list_sources(p)
        table.add_row(p, str(len(sources)))

    console.print(table)


@main.command()
@click.argument("project")
def info(project):
    """Show project info."""
    from atenea.storage import list_sources, get_project_path, load_json
    import os

    console.print(f"\n[bold]{project}[/bold]")

    sources = list_sources(project)
    console.print(f"Sources: {len(sources)}")
    for sid in sources:
        console.print(f"  - {sid}")

    for filename in ["clean-md.json", "data.json", "preguntas.json"]:
        path = get_project_path(project, filename)
        if os.path.exists(path):
            size = os.path.getsize(path)
            console.print(f"{filename}: {size:,} bytes")
        else:
            console.print(f"{filename}: [dim]not created[/dim]")


# ============================================================
# Init & Doctor
# ============================================================

@main.command()
@click.option("--data-dir", default=None,
              help="Custom data directory (default: ~/.atenea/data)")
def init(data_dir):
    """Initialize Atenea data directory."""
    from pathlib import Path
    from config import defaults

    target = Path(data_dir) if data_dir else Path(defaults.DEFAULT_DATA_DIR)
    target.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]OK[/green] Data directory: {target}")
    console.print(f"Create your first project:")
    console.print(f"  atenea convert <pdf> --project <name>")


@main.command()
def doctor():
    """Check system dependencies."""
    import sys
    checks = []

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    checks.append(("Python >= 3.10", py_ver, sys.version_info >= (3, 10)))

    from pathlib import Path
    from config import defaults
    data_dir = Path(defaults.DEFAULT_DATA_DIR)
    checks.append(("Data directory", str(data_dir), data_dir.exists()))

    for pkg in ["click", "rich", "litellm", "langdetect"]:
        try:
            __import__(pkg)
            checks.append((pkg, "ok", True))
        except ImportError:
            checks.append((pkg, "MISSING", False))

    try:
        import marker
        checks.append(("marker-pdf", "ok", True))
    except ImportError:
        checks.append(("marker-pdf", "missing (needed for convert)", False))

    import os
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY") or
                   os.environ.get("OPENAI_API_KEY") or
                   os.environ.get("ANTHROPIC_API_KEY"))
    checks.append(("LLM API key", "ok" if has_key else "MISSING", has_key))

    table = Table(title="Doctor")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("", justify="center")

    for name, status, ok in checks:
        icon = "[green]ok[/green]" if ok else "[red]no[/red]"
        table.add_row(name, status, icon)

    console.print(table)


if __name__ == "__main__":
    main()
