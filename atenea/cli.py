"""
atenea/cli.py — Command Line Interface

Entry point for the Atenea CLI. Each pipeline step is a separate command,
allowing step-by-step execution with human review between steps.

Usage:
    atenea convert <pdf> --project <name>     # Step 1: PDF → Markdown
    atenea chunk <project>                     # Step 2: Markdown → clean-md.json
    atenea extract <project>                   # Step 3: Extract CSPOJ → data.json
    atenea generate <project>                  # Step 4: Generate questions
    atenea test <project>                      # Step 5: Run adaptive test
    atenea analyze <project>                   # Step 6: Show analytics
    atenea advisor <project>                   # AI Advisor session
    atenea pipeline <pdf> --project <name>     # Run full pipeline
    atenea projects                             # List all projects
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
    """Atenea — Adaptive learning from documents using CSPOJ ontology."""
    pass


# ============================================================
# Step 1: PDF → Markdown
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
    console.print(f"[green]✓[/green] Markdown saved to: {result}")


# ============================================================
# Step 2: Markdown → clean-md.json
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
    console.print(f"[green]✓[/green] clean-md.json: {n_sections} sections, "
                  f"{n_lines} lines, {n_keywords} keywords")


# ============================================================
# Step 3: Knowledge Extraction → data.json
# ============================================================

@main.command()
@click.argument("project")
@click.option("--source", "-s", default=None,
              help="Source ID to extract from (default: latest)")
@click.option("--model", "-m", default=None,
              help="Override LLM model (litellm format)")
@click.option("--stats/--no-stats", default=True,
              help="Show extraction confidence metrics")
def extract(project, source, model, stats):
    """Extract CSPOJ knowledge structures from clean-md.json."""
    from atenea.extract import run_extraction
    result = run_extraction(project, source_id=source, model=model)
    n_points = len(result.get("points", []))
    n_paths = len(result.get("paths", []))
    n_sets = len(result.get("sets", []))
    n_maps = len(result.get("maps", []))
    console.print(f"[green]✓[/green] data.json: {n_points} points, "
                  f"{n_paths} paths, {n_sets} sets, {n_maps} maps")

    if stats:
        from atenea.extract import compute_extraction_stats
        from atenea.storage import get_source_path, list_sources, load_json
        src = source
        if src is None:
            srcs = list_sources(project)
            src = srcs[-1] if srcs else None
        if src:
            clean_md_path = get_source_path(project, src, "clean-md.json")
            clean_md = load_json(clean_md_path) or {}
            if clean_md:
                ext_stats = compute_extraction_stats(result, clean_md)
                table = Table(title="Extraction Stats")
                table.add_column("Metric", style="bold")
                table.add_column("Value", justify="right")
                table.add_column("Target", justify="right")
                for key, metric in ext_stats.items():
                    if isinstance(metric, dict):
                        table.add_row(
                            key,
                            f"{metric.get('value', 0):.1%}",
                            f"{metric.get('target', 'N/A')}",
                        )
                console.print(table)


# ============================================================
# Step 4: Question Generation
# ============================================================

@main.command()
@click.argument("project")
@click.option("--source", "-s", default=None, help="Source ID (default: latest)")
@click.option("--model", "-m", default=None, help="Override LLM model")
@click.option("--lite/--full", default=True,
              help="Lite mode: free-text only, no LLM calls (default: lite)")
@click.option("--natural/--template", default=False,
              help="Use LLM to reformulate questions in natural language")
@click.option("--mc-only", is_flag=True, default=False,
              help="Generate only multiple-choice questions")
@click.option("--max-paths", default=None, type=int,
              help="Max paths to process in lite mode")
def generate(project, source, model, lite, natural, mc_only, max_paths):
    """Generate questions from CSPOJ knowledge structures."""
    from atenea.generate import generate_questions, generate_questions_lite
    from atenea.generate import Q_MULTIPLE_CHOICE
    if lite and not mc_only:
        result = generate_questions_lite(
            project, source_id=source, model=model,
            max_paths=max_paths or 999,
        )
    else:
        question_types = [Q_MULTIPLE_CHOICE] if mc_only else None
        result = generate_questions(
            project, source_id=source, model=model,
            question_types=question_types, natural=natural,
        )
    n = len(result.get("questions", []))
    by_type = result.get("stats", {}).get("by_type", {})
    console.print(f"[green]✓[/green] preguntas.json: {n} questions generated")
    if by_type:
        for qtype, count in by_type.items():
            console.print(f"  {qtype}: {count}")


# ============================================================
# Step 5: Adaptive Test
# ============================================================

@main.command()
@click.argument("project")
@click.option("-n", "--n-questions", default=None, type=int,
              help="Number of questions (default from config)")
@click.option("--source", "-s", default=None, help="Source ID (default: latest)")
@click.option("--model", "-m", default=None, help="Override LLM model for evaluation")
def test(project, n_questions, source, model):
    """Run an adaptive test session."""
    from atenea.test_engine import run_test
    run_test(project, source_id=source, n_questions=n_questions, model=model)


# ============================================================
# Step 6: Analytics
# ============================================================

@main.command()
@click.argument("project")
def analyze(project):
    """Show learning analytics and progress."""
    from atenea.analyze import run_analytics
    run_analytics(project)


# ============================================================
# AI Advisor
# ============================================================

@main.command()
@click.argument("project")
@click.option("--feedback", "-f", default=None,
              help="Quick feedback in natural language")
@click.option("--suggest/--no-suggest", default=False,
              help="Show proactive suggestions only")
@click.option("--evolve-prompts/--no-evolve-prompts", default=False,
              help="Propose prompt improvements")
@click.option("--model", "-m", default=None, help="Override LLM model")
def advisor(project, feedback, suggest, evolve_prompts, model):
    """AI Advisor — meta-learning loop for system improvement."""
    from atenea.advisor import run_advisor_session
    run_advisor_session(
        project, feedback=feedback, suggest_only=suggest,
        evolve_prompts=evolve_prompts, model=model,
    )


# ============================================================
# Full Pipeline
# ============================================================

@main.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option("--project", "-p", required=True, help="Project name")
@click.option("--use-llm/--no-llm", default=False,
              help="Use Marker's LLM-assisted mode")
def pipeline(pdf_path, project, use_llm):
    """Run the full pipeline: convert → chunk → extract → generate."""
    console.print("[bold]Running full Atenea pipeline...[/bold]")

    console.print("\n[bold]Step 1:[/bold] Converting PDF to markdown...")
    from atenea.convert import convert_pdf_to_markdown
    convert_pdf_to_markdown(pdf_path, project, use_llm=use_llm)
    console.print("[green]✓[/green] Convert complete")

    console.print("\n[bold]Step 2:[/bold] Chunking markdown...")
    from atenea.chunk import chunk_markdown
    chunk_markdown(project)
    console.print("[green]✓[/green] Chunk complete")

    console.print("\n[bold]Step 3:[/bold] Extracting knowledge...")
    from atenea.extract import run_extraction
    run_extraction(project)
    console.print("[green]✓[/green] Extract complete")

    console.print("\n[bold]Step 4:[/bold] Generating questions...")
    from atenea.generate import generate_questions_lite
    generate_questions_lite(project)
    console.print("[green]✓[/green] Generate complete")

    console.print("\n[green bold]Pipeline complete.[/green bold]")


# ============================================================
# Project Management
# ============================================================

@main.command()
def projects():
    """List all learning projects."""
    from atenea.storage import list_projects
    project_list = list_projects()
    if not project_list:
        console.print("[dim]No projects found. Create one with:[/dim]")
        console.print("  atenea convert <pdf> --project <name>")
        return

    table = Table(title="Atenea Projects")
    table.add_column("Project", style="bold")
    table.add_column("Sources", justify="right")
    table.add_column("Status")

    from atenea.storage import list_sources, get_project_path
    import os
    for p in project_list:
        sources = list_sources(p)
        has_data = os.path.exists(get_project_path(p, "data.json"))
        status = "[green]extracted[/green]" if has_data else "[yellow]pending[/yellow]"
        table.add_row(p, str(len(sources)), status)

    console.print(table)


@main.command()
@click.argument("project")
def info(project):
    """Show detailed info about a project."""
    from atenea.storage import (
        get_project_path, list_sources, load_json
    )
    import os

    console.print(f"\n[bold]Project:[/bold] {project}")

    sources = list_sources(project)
    console.print(f"[bold]Sources:[/bold] {len(sources)}")
    for sid in sources:
        console.print(f"  - {sid}")

    for filename in ["clean-md.json", "data.json", "preguntas.json", "analisis.json"]:
        path = get_project_path(project, filename)
        if os.path.exists(path):
            data = load_json(path)
            size = os.path.getsize(path)
            console.print(f"[bold]{filename}:[/bold] {size:,} bytes")
        else:
            console.print(f"[bold]{filename}:[/bold] [dim]not yet created[/dim]")


# ============================================================
# Developer UI
# ============================================================

@main.command()
@click.option("--port", "-p", default=8080, help="Port for the UI server")
@click.option("--reload/--no-reload", default=False, help="Auto-reload on code changes")
def ui(port, reload):
    """Launch the developer dashboard (NiceGUI)."""
    from atenea.ui.app import start_ui
    console.print(f"[bold]Starting Atenea Developer Dashboard on port {port}...[/bold]")
    start_ui(port=port, reload=reload)


# ============================================================
# Init & Doctor
# ============================================================

@main.command()
@click.option("--data-dir", default=None,
              help="Custom data directory (default: ~/.atenea/data)")
def init(data_dir):
    """Initialize Atenea data directory and verify setup."""
    from pathlib import Path
    from config import defaults

    target = Path(data_dir) if data_dir else Path(defaults.DEFAULT_DATA_DIR)
    target.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]✓[/green] Data directory: {target}")

    if data_dir:
        console.print(f"\n  To persist this setting, add to your shell profile:")
        console.print(f"  [bold]export ATENEA_DATA_DIR={data_dir}[/bold]")

    console.print(f"\n[green bold]Atenea initialized.[/green bold]")
    console.print(f"  Create your first project:")
    console.print(f"  atenea convert <pdf> --project <name>")


@main.command()
def doctor():
    """Check system dependencies and configuration."""
    from pathlib import Path
    from config import defaults
    import shutil

    checks = []

    # 1. Python version
    import sys
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    checks.append(("Python >= 3.10", py_ver, py_ok))

    # 2. Data directory
    data_dir = Path(defaults.DEFAULT_DATA_DIR)
    checks.append(("Data directory", str(data_dir), data_dir.exists()))

    # 3. Core dependencies
    for pkg in ["click", "rich", "litellm", "langdetect"]:
        try:
            __import__(pkg)
            checks.append((f"Package: {pkg}", "installed", True))
        except ImportError:
            checks.append((f"Package: {pkg}", "MISSING", False))

    # 4. Optional: marker-pdf
    try:
        import marker
        checks.append(("Package: marker-pdf", "installed", True))
    except ImportError:
        checks.append(("Package: marker-pdf", "not installed (needed for PDF conversion)", False))

    # 5. Optional: nicegui
    try:
        import nicegui
        checks.append(("Package: nicegui", "installed", True))
    except ImportError:
        checks.append(("Package: nicegui", "not installed (needed for UI)", False))

    # 6. LLM API key
    import os
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY") or
                   os.environ.get("OPENAI_API_KEY") or
                   os.environ.get("ANTHROPIC_API_KEY"))
    checks.append(("LLM API key", "configured" if has_key else "MISSING (set DEEPSEEK_API_KEY or OPENAI_API_KEY)", has_key))

    # Display
    table = Table(title="Atenea Doctor")
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("OK?", justify="center")

    all_ok = True
    for name, status, ok in checks:
        icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
        table.add_row(name, status, icon)
        if not ok:
            all_ok = False

    console.print(table)

    if all_ok:
        console.print("\n[green bold]All checks passed.[/green bold]")
    else:
        console.print("\n[yellow]Some checks failed. Install missing packages with:[/yellow]")
        console.print("  pip install 'atenea[all]'")


if __name__ == "__main__":
    main()
