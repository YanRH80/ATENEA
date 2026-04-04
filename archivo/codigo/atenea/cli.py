"""
atenea/cli.py — Command Line Interface

Usage:
    atenea add <pdf> -p <project>         # Ingest PDF
    atenea study <project>                # LLM condense → knowledge.json
    atenea generate <project> [-n 25]     # LLM generate MIR questions
    atenea test <project> [-n 25]         # Interactive test in terminal
    atenea review <project>               # Coverage + gaps
    atenea show <project> [keywords|graph|coverage]
    atenea export md <project>            # → .md (Obsidian)
    atenea export csv <project>           # → .csv (Anki)
    atenea projects                       # List projects
    atenea info <project>                 # Project stats
    atenea doctor                         # Check deps
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
# Add PDF
# ============================================================

@main.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option("--project", "-p", required=True, help="Project name")
def add(pdf_path, project):
    """Ingest a PDF: extract text, tables, and images."""
    from atenea.ingest import ingest_pdf
    console.print(f"[bold]Ingesting:[/bold] {pdf_path}")
    result = ingest_pdf(pdf_path, project)
    console.print(f"[green]OK[/green] {result['source_id']}: "
                  f"{result['pages']} pages, "
                  f"{result['tables']} tables, "
                  f"{result['images']} images, "
                  f"{result['total_chars']:,} chars")


# ============================================================
# Study: condense source → knowledge.json
# ============================================================

@main.command()
@click.argument("project")
@click.option("--source", "-s", default=None, help="Source ID (default: latest)")
@click.option("--model", "-m", default=None, help="Override LLM model")
def study(project, source, model):
    """Extract knowledge from source text via LLM."""
    import logging
    from atenea.study import run_study
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    console.print(f"[bold]Studying:[/bold] {project}" +
                  (f" (source {source})" if source else ""))
    console.print("[dim]Processing in batches (5 pages each)...[/dim]")
    result = run_study(project, source_id=source, model=model)
    n_kw = len(result.get("keywords", []))
    n_as = len(result.get("associations", []))
    n_sq = len(result.get("sequences", []))
    n_st = len(result.get("sets", []))
    console.print(f"[green]OK[/green] knowledge.json: "
                  f"{n_kw} keywords, {n_as} associations, "
                  f"{n_sq} sequences, {n_st} sets")


# ============================================================
# Generate: knowledge → MIR questions
# ============================================================

@main.command()
@click.argument("project")
@click.option("--count", "-n", default=25, help="Number of questions")
@click.option("--model", "-m", default=None, help="Override LLM model")
def generate(project, count, model):
    """Generate MIR-style questions from knowledge graph."""
    import logging
    from atenea.generate import run_generate
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    console.print(f"[bold]Generating:[/bold] {count} questions for {project}")
    result = run_generate(project, n=count, model=model)
    n_q = len(result.get("questions", []))
    console.print(f"[green]OK[/green] questions.json: {n_q} total questions")


# ============================================================
# Test: interactive MIR test in terminal
# ============================================================

@main.command()
@click.argument("project")
@click.option("--count", "-n", default=25, help="Number of questions")
def test(project, count):
    """Run an interactive MIR test session."""
    from atenea.test_engine import run_test
    run_test(project, n=count)


# ============================================================
# Review: coverage + gaps
# ============================================================

@main.command()
@click.argument("project")
@click.option("--llm", is_flag=True, help="Use LLM for gap analysis")
@click.option("--model", "-m", default=None, help="Override LLM model")
def review(project, llm, model):
    """Analyze coverage and identify knowledge gaps."""
    from atenea.review import run_review
    run_review(project, use_llm=llm, model=model)


# ============================================================
# Show: display knowledge data
# ============================================================

@main.command()
@click.argument("project")
@click.argument("view", type=click.Choice(["keywords", "graph", "coverage"]))
def show(project, view):
    """Display knowledge data in terminal."""
    from atenea import storage

    if view == "keywords":
        _show_keywords(project)
    elif view == "graph":
        _show_graph(project)
    elif view == "coverage":
        from atenea.review import display_coverage
        display_coverage(project)


def _show_keywords(project):
    """Show keywords with status indicators."""
    from atenea import storage
    knowledge = storage.load_json(
        str(storage.get_project_path(project, "knowledge.json")))
    coverage = storage.load_json(
        str(storage.get_project_path(project, "coverage.json"))) or {"items": {}}
    items = coverage.get("items", {})

    keywords = knowledge.get("keywords", [])
    if not keywords:
        console.print("[dim]No keywords yet. Run 'atenea study' first.[/dim]")
        return

    # Count by status
    status_counts = {"known": 0, "testing": 0, "unknown": 0}
    for kw in keywords:
        status = items.get(kw["term"], {}).get("status", "unknown")
        status_counts[status] += 1

    console.print(f"\n[bold]Keywords — {project}[/bold] ({len(keywords)} total)")
    console.print(f"  [green]✅ known ({status_counts['known']})[/green]  "
                  f"[yellow]🔄 testing ({status_counts['testing']})[/yellow]  "
                  f"[red]❓ unknown ({status_counts['unknown']})[/red]\n")

    for kw in keywords:
        term = kw["term"]
        status = items.get(term, {}).get("status", "unknown")
        icon = {"known": "[green]✅[/green]", "testing": "[yellow]🔄[/yellow]",
                "unknown": "[red]❓[/red]"}.get(status, "❓")
        tags = " ".join(f"[dim][{t}][/dim]" for t in kw.get("tags", []))
        source = kw.get("source", "")
        page = kw.get("page", "")
        ref = f"[dim]{source} p.{page}[/dim]" if source and page else ""
        console.print(f"  {icon} {term}  {tags}  {ref}")

    console.print()


def _show_graph(project):
    """Show sequences as visual chains."""
    from atenea import storage
    knowledge = storage.load_json(
        str(storage.get_project_path(project, "knowledge.json")))
    coverage = storage.load_json(
        str(storage.get_project_path(project, "coverage.json"))) or {"items": {}}
    items = coverage.get("items", {})

    sequences = knowledge.get("sequences", [])
    if not sequences:
        console.print("[dim]No sequences yet. Run 'atenea study' first.[/dim]")
        return

    console.print(f"\n[bold]Sequences — {project}[/bold] ({len(sequences)} total)")
    console.print(f"[dim](7±2 nodes each)[/dim]\n")

    for seq in sequences:
        desc = seq.get("description", "")[:60]
        nodes = seq.get("nodes", [])
        seq_id = seq.get("id", "")

        # Build visual chain
        node_parts = []
        status_parts = []
        for node in nodes:
            status = items.get(node, {}).get("status", "unknown")
            icon = {"known": "✅", "testing": "🔄", "unknown": "❓"}.get(status, "❓")
            node_parts.append(f"[{node[:12]}]")
            status_parts.append(f"  {icon}  ")

        chain = "──→".join(node_parts)
        statuses = "   ".join(status_parts)

        console.print(f"[bold]{seq_id}:[/bold] {desc}")
        console.print(f"  {chain}")
        console.print(f"  {statuses}")
        console.print()


# ============================================================
# Export: transforms to external formats
# ============================================================

@main.group()
def export():
    """Export data to external formats."""
    pass


@export.command("md")
@click.argument("project")
@click.option("--output", "-o", default=None, help="Output file path")
def export_md_cmd(project, output):
    """Export knowledge as Obsidian markdown."""
    from atenea.export import export_md
    path = export_md(project, output_path=output)
    console.print(f"[green]OK[/green] Exported to {path}")


@export.command("csv")
@click.argument("project")
@click.option("--output", "-o", default=None, help="Output file path")
def export_csv_cmd(project, output):
    """Export questions as Anki CSV."""
    from atenea.export import export_csv
    path = export_csv(project, output_path=output)
    console.print(f"[green]OK[/green] Exported to {path}")


# ============================================================
# Project Management
# ============================================================

@main.command()
def projects():
    """List all projects."""
    from atenea.storage import list_projects, list_sources
    project_list = list_projects()
    if not project_list:
        console.print("[dim]No projects. Create one with:[/dim]")
        console.print("  atenea add <pdf> -p <name>")
        return

    table = Table(title="Projects")
    table.add_column("Project", style="bold")
    table.add_column("Sources", justify="right")
    for p in project_list:
        table.add_row(p, str(len(list_sources(p))))
    console.print(table)


@main.command()
@click.argument("project")
def info(project):
    """Show project info."""
    from atenea.storage import list_sources, get_project_path, load_json
    import os

    project_data = load_json(str(get_project_path(project, "project.json")))
    if not project_data:
        console.print(f"[red]Project '{project}' not found[/red]")
        return

    console.print(f"\n[bold]{project}[/bold]")

    sources = project_data.get("sources", [])
    console.print(f"Sources: {len(sources)}")
    for s in sources:
        console.print(f"  {s['source_id']}: {s['filename']} [{s['citekey']}]")

    for filename in ["knowledge.json", "questions.json", "coverage.json", "sessions.json"]:
        path = get_project_path(project, filename)
        if os.path.exists(str(path)):
            size = os.path.getsize(str(path))
            console.print(f"{filename}: {size:,} bytes")
        else:
            console.print(f"{filename}: [dim]not created[/dim]")


# ============================================================
# Init & Doctor
# ============================================================

@main.command()
@click.option("--data-dir", default=None, help="Custom data directory")
def init(data_dir):
    """Initialize Atenea data directory."""
    from pathlib import Path
    from config import defaults
    target = Path(data_dir) if data_dir else Path(defaults.DEFAULT_DATA_DIR)
    target.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]OK[/green] Data directory: {target}")
    console.print(f"Add your first PDF:")
    console.print(f"  atenea add <pdf> -p <project>")


@main.command()
def doctor():
    """Check system dependencies."""
    import sys
    checks = []

    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    checks.append(("Python >= 3.10", py_ver, sys.version_info >= (3, 10)))

    from pathlib import Path
    from config import defaults
    checks.append(("Data dir", str(Path(defaults.DEFAULT_DATA_DIR)),
                    Path(defaults.DEFAULT_DATA_DIR).exists()))

    for pkg in ["click", "rich", "litellm", "pdfplumber", "fitz"]:
        try:
            __import__(pkg)
            checks.append((pkg, "ok", True))
        except ImportError:
            checks.append((pkg, "MISSING", False))

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
        table.add_row(name, status, "[green]ok[/green]" if ok else "[red]no[/red]")
    console.print(table)


if __name__ == "__main__":
    main()
