"""
atenea/cli.py — Command Line Interface

Usage:
    atenea sync <project> [--collection "X"]   # Sync Zotero → local
    atenea study <project>                     # LLM condense → knowledge.json
    atenea generate <project> [-n 25]          # LLM generate MIR questions
    atenea test <project> [-n 25]              # Interactive test in terminal
    atenea review <project>                    # Coverage + gaps
    atenea show <project> [keywords|graph|coverage]
    atenea export md|csv <project>
    atenea reset <project> [--hard]
    atenea projects / info / doctor
"""

import logging
import os
import time

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table
from rich.tree import Tree

from config import theme

console = Console()
log = logging.getLogger(__name__)


def _load_dotenv():
    """Load .env at CLI entry point — single place for side effects."""
    from dotenv import load_dotenv
    load_dotenv()


def _numbered_choice(title, options, show_info=None):
    """Interactive numbered selection. Returns selected index or None.

    Args:
        title: Header text
        options: list of display strings
        show_info: optional list of extra info lines (same length as options)
    """
    console.print(f"\n[{theme.HEADER}]{title}[/]")
    console.print(f"[{theme.NAV_HINT}]Type a number to select, 'q' to cancel[/]\n")

    for i, opt in enumerate(options, 1):
        console.print(f"  [{theme.NAV_OPTION_NUMBER}]{i:>3}[/]  {opt}")
        if show_info and i - 1 < len(show_info) and show_info[i - 1]:
            console.print(f"       [{theme.MUTED}]{show_info[i - 1]}[/]")

    console.print()
    while True:
        raw = console.input(f"[{theme.NAV_PROMPT_STYLE}]> [/]").strip()
        if raw.lower() == "q":
            return None
        try:
            idx = int(raw)
            if 1 <= idx <= len(options):
                return idx - 1
        except ValueError:
            pass
        console.print(f"[{theme.ERROR}]Enter 1-{len(options)} or 'q'[/]")


def _location_banner(project=None, collection=None, view=None):
    """Show where the user is + what they can do."""
    parts = ["ATENEA"]
    if project:
        parts.append(project)
    if collection:
        parts.append(collection)
    if view:
        parts.append(view)

    breadcrumb = " > ".join(parts)
    console.print(f"\n[{theme.MUTED}]{breadcrumb}[/]")


# ============================================================
# MAIN GROUP
# ============================================================

@click.group()
@click.version_option(package_name="atenea")
def main():
    """Atenea — Adaptive learning from documents."""
    _load_dotenv()


# ============================================================
# SYNC: Zotero → local
# ============================================================

@main.command()
@click.argument("project")
@click.option("--collection", "-c", default=None, help="Zotero collection name (interactive if omitted)")
def sync(project, collection):
    """Sync PDFs and metadata from a Zotero collection."""
    t0 = time.time()
    _location_banner(project, view="sync")

    from atenea import zotero, storage

    # Connect
    with _spinner("Connecting to Zotero..."):
        client = zotero.connect()

    # List collections
    with _spinner("Loading collections..."):
        all_collections = zotero.list_collections(client)

    if not all_collections:
        console.print(f"[{theme.ERROR}]No collections found in your Zotero library.[/]")
        return

    # Navigate to collection
    if collection:
        coll = zotero.find_collection_by_name(all_collections, collection)
        if not coll:
            console.print(f"[{theme.ERROR}]Collection '{collection}' not found.[/]")
            _show_available_collections(all_collections)
            return
    else:
        coll = _navigate_collections(all_collections)
        if coll is None:
            console.print(f"[{theme.MUTED}]Cancelled.[/]")
            return

    console.print(f"\n[{theme.SUCCESS}]Selected:[/] {coll['name']} ({coll['num_items']} items)")

    # Sync with progress
    console.print()
    with Progress(
        SpinnerColumn(theme.PROGRESS_SPINNER),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Syncing...", total=5)

        def on_progress(step, total, msg):
            progress.update(task, completed=step, description=msg)

        result = zotero.sync(client, project, coll["key"], on_progress=on_progress)

    # Display results
    elapsed = time.time() - t0
    _display_sync_result(result, project, elapsed)

    # Show bibliography
    bib = storage.load_json(result["bibliography_path"])
    if isinstance(bib, list) and bib:
        _display_bibliography(bib, project)


def _navigate_collections(all_collections, parent_key=None, depth=0):
    """Interactive collection navigation with numbered options."""
    from atenea import zotero

    children = zotero.get_subcollections(all_collections, parent_key)
    if not children:
        return None

    names = [f"{c['name']} ({c['num_items']} items)" for c in children]

    # Check which have subcollections
    info = []
    for c in children:
        subs = zotero.get_subcollections(all_collections, c["key"])
        if subs:
            info.append(f"{len(subs)} subcollections")
        else:
            info.append(None)

    if depth > 0:
        names.insert(0, ".. (back)")
        info.insert(0, None)

    title = "Select collection" if depth == 0 else "Navigate"
    choice = _numbered_choice(title, names, info)

    if choice is None:
        return None

    # Handle "back"
    if depth > 0 and choice == 0:
        return None  # Caller handles going up

    actual_idx = choice - (1 if depth > 0 else 0)
    selected = children[actual_idx]

    # Check for subcollections
    subs = zotero.get_subcollections(all_collections, selected["key"])
    if subs:
        sub_names = [f"[USE THIS] {selected['name']}", "Browse subcollections..."]
        sub_choice = _numbered_choice(
            f"{selected['name']}",
            sub_names,
            [f"{selected['num_items']} items in this collection",
             f"{len(subs)} subcollections available"]
        )
        if sub_choice == 0:
            return selected
        elif sub_choice == 1:
            result = _navigate_collections(all_collections, selected["key"], depth + 1)
            return result if result else selected
        return None

    return selected


def _show_available_collections(collections):
    """Show all collections as a flat list."""
    console.print(f"\n[{theme.HEADER}]Available collections:[/]")
    for c in collections:
        indent = "  " if c["parent"] else ""
        console.print(f"  {indent}{c['name']} ({c['num_items']} items)")


def _display_sync_result(result, project, elapsed):
    """Show sync summary panel."""
    lines = [
        f"[{theme.SUCCESS}]New:[/]      {result['new']}",
        f"[{theme.INFO}]Existing:[/] {result['existing']}",
        f"[{theme.WARNING}]Removed:[/]  {result['removed']}",
    ]
    if result.get("skipped_no_pdf", 0) > 0:
        lines.append(f"[{theme.MUTED}]No PDF:[/]   {result['skipped_no_pdf']}")
    if result.get("errors", 0) > 0:
        lines.append(f"[{theme.ERROR}]Errors:[/]   {result['errors']}")

    lines.append(f"")
    lines.append(f"[{theme.MUTED}]Total items: {result['total_items']} | "
                 f"Runtime: {elapsed:.1f}s[/]")

    panel = Panel(
        "\n".join(lines),
        title=f"[{theme.HEADER}]Sync — {project}[/]",
        border_style=theme.PANEL_BORDER,
    )
    console.print(panel)


def _display_bibliography(bib, project):
    """Show bibliography table with citations, evidence levels, and summaries."""
    _location_banner(project, view="bibliography")

    # Filter out removed
    active = [e for e in bib if not e.get("removed")]
    if not active:
        console.print(f"[{theme.MUTED}]No active documents.[/]")
        return

    table = Table(
        title=f"Documents ({len(active)})",
        border_style=theme.TABLE_BORDER,
        show_lines=True,
    )
    table.add_column("#", style=theme.NAV_OPTION_NUMBER, width=3, justify="right")
    table.add_column("Citation", style="white", ratio=4)
    table.add_column("Ev.", style="bold", width=4, justify="center")
    table.add_column("Gr.", width=3, justify="center")
    table.add_column("Summary", style=theme.MUTED, ratio=3)

    for i, entry in enumerate(active, 1):
        citation = entry.get("citation_formatted", entry.get("title", "?"))
        ev_level = entry.get("evidence_level", "?")
        ev_color = theme.EVIDENCE_COLORS.get(ev_level, "dim")
        grade = entry.get("recommendation_grade", "?")
        abstract = (entry.get("abstract", "") or "")[:80]
        if abstract and len(entry.get("abstract", "")) > 80:
            abstract += "..."

        table.add_row(
            str(i),
            citation,
            f"[{ev_color}]{ev_level}[/]",
            grade,
            abstract if abstract else "[dim]No abstract[/]",
        )

    console.print(table)

    # Stats summary
    ev_counts = {}
    for e in active:
        ev = e.get("evidence_level", "?")
        ev_counts[ev] = ev_counts.get(ev, 0) + 1

    ev_parts = [f"[{theme.EVIDENCE_COLORS.get(k, 'dim')}]{k}[/]:{v}"
                for k, v in sorted(ev_counts.items())]
    console.print(f"\n[{theme.MUTED}]Evidence distribution: {' | '.join(ev_parts)}[/]")


# ============================================================
# RESET
# ============================================================

@main.command()
@click.argument("project")
@click.option("--hard", is_flag=True, help="Delete everything including sources and bibliography")
@click.confirmation_option(prompt="This will delete project data. Continue?")
def reset(project, hard):
    """Reset project data (outputs, or everything with --hard)."""
    from atenea.zotero import reset_project
    t0 = time.time()
    _location_banner(project, view="reset")

    deleted = reset_project(project, hard=hard)
    elapsed = time.time() - t0

    if deleted:
        for d in deleted:
            console.print(f"  [{theme.ERROR}]deleted[/] {d}")
        console.print(f"\n[{theme.MUTED}]Runtime: {elapsed:.2f}s[/]")
    else:
        console.print(f"[{theme.MUTED}]Nothing to delete.[/]")


# ============================================================
# ADD PDF (legacy — prefer sync)
# ============================================================

@main.command()
@click.argument("pdf_path", type=click.Path(exists=True))
@click.option("--project", "-p", required=True, help="Project name")
def add(pdf_path, project):
    """Ingest a PDF: extract text, tables, and images."""
    t0 = time.time()
    from atenea.ingest import ingest_pdf
    _location_banner(project, view="add")
    console.print(f"[bold]Ingesting:[/bold] {pdf_path}")
    result = ingest_pdf(pdf_path, project)
    elapsed = time.time() - t0
    console.print(f"[{theme.SUCCESS}]OK[/] {result['source_id']}: "
                  f"{result['pages']} pages, "
                  f"{result['tables']} tables, "
                  f"{result['images']} images, "
                  f"{result['total_chars']:,} chars "
                  f"[{theme.MUTED}]({elapsed:.1f}s)[/]")


# ============================================================
# STUDY
# ============================================================

@main.command()
@click.argument("project")
@click.option("--source", "-s", default=None, help="Source ID (default: latest)")
@click.option("--model", "-m", default=None, help="Override LLM model")
def study(project, source, model):
    """Extract knowledge from source text via LLM."""
    t0 = time.time()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _location_banner(project, view="study")
    from atenea.study import run_study
    console.print(f"[dim]Processing in batches...[/dim]")
    result = run_study(project, source_id=source, model=model)
    elapsed = time.time() - t0
    n_kw = len(result.get("keywords", []))
    n_as = len(result.get("associations", []))
    n_sq = len(result.get("sequences", []))
    n_st = len(result.get("sets", []))
    console.print(f"[{theme.SUCCESS}]OK[/] knowledge.json: "
                  f"{n_kw} keywords, {n_as} associations, "
                  f"{n_sq} sequences, {n_st} sets "
                  f"[{theme.MUTED}]({elapsed:.1f}s)[/]")


# ============================================================
# GENERATE
# ============================================================

@main.command()
@click.argument("project")
@click.option("--count", "-n", default=25, help="Number of questions")
@click.option("--model", "-m", default=None, help="Override LLM model")
def generate(project, count, model):
    """Generate MIR-style questions from knowledge graph."""
    t0 = time.time()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _location_banner(project, view="generate")
    from atenea.generate import run_generate
    result = run_generate(project, n=count, model=model)
    elapsed = time.time() - t0
    n_q = len(result.get("questions", []))
    console.print(f"[{theme.SUCCESS}]OK[/] questions.json: {n_q} total "
                  f"[{theme.MUTED}]({elapsed:.1f}s)[/]")


# ============================================================
# TEST
# ============================================================

@main.command()
@click.argument("project")
@click.option("--count", "-n", default=25, help="Number of questions")
def test(project, count):
    """Run an interactive MIR test session."""
    _location_banner(project, view="test")
    from atenea.test_engine import run_test
    run_test(project, n=count)


# ============================================================
# REVIEW
# ============================================================

@main.command()
@click.argument("project")
@click.option("--llm", is_flag=True, help="Use LLM for gap analysis")
@click.option("--model", "-m", default=None, help="Override LLM model")
def review(project, llm, model):
    """Analyze coverage and identify knowledge gaps."""
    _location_banner(project, view="review")
    from atenea.review import run_review
    run_review(project, use_llm=llm, model=model)


# ============================================================
# SHOW
# ============================================================

@main.command()
@click.argument("project")
@click.argument("view", type=click.Choice(["keywords", "graph", "coverage"]))
def show(project, view):
    """Display knowledge data in terminal."""
    _location_banner(project, view=view)
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
        console.print(f"[{theme.MUTED}]No keywords yet. Run 'atenea study' first.[/]")
        return

    status_counts = {"known": 0, "testing": 0, "unknown": 0}
    for kw in keywords:
        status = items.get(kw["term"], {}).get("status", "unknown")
        status_counts[status] += 1

    console.print(f"\n[bold]Keywords ({len(keywords)})[/bold]")
    console.print(f"  [{theme.STATUS_COLORS['known']}]{theme.STATUS_ICONS['known']} known ({status_counts['known']})[/]  "
                  f"[{theme.STATUS_COLORS['testing']}]{theme.STATUS_ICONS['testing']} testing ({status_counts['testing']})[/]  "
                  f"[{theme.STATUS_COLORS['unknown']}]{theme.STATUS_ICONS['unknown']} unknown ({status_counts['unknown']})[/]\n")

    for kw in keywords:
        term = kw["term"]
        status = items.get(term, {}).get("status", "unknown")
        icon = theme.STATUS_ICONS.get(status, theme.STATUS_ICONS["unknown"])
        color = theme.STATUS_COLORS.get(status, "red")
        tags = " ".join(f"[dim][{t}][/dim]" for t in kw.get("tags", []))
        ref = f"[dim]{kw.get('source', '')} p.{kw.get('page', '')}[/dim]"
        console.print(f"  [{color}]{icon}[/] {term}  {tags}  {ref}")

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
        console.print(f"[{theme.MUTED}]No sequences yet. Run 'atenea study' first.[/]")
        return

    console.print(f"\n[bold]Sequences ({len(sequences)})[/bold]\n")

    for seq in sequences:
        desc = seq.get("description", "")[:60]
        nodes = seq.get("nodes", [])

        node_parts = []
        for node in nodes:
            status = items.get(node, {}).get("status", "unknown")
            color = theme.STATUS_COLORS.get(status, "red")
            node_parts.append(f"[{color}]{node[:15]}[/]")

        chain = " -> ".join(node_parts)
        console.print(f"  [{theme.MUTED}]{seq.get('id', '')}[/] {desc}")
        console.print(f"  {chain}\n")


# ============================================================
# EXPORT
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
    t0 = time.time()
    from atenea.export import export_md
    path = export_md(project, output_path=output)
    console.print(f"[{theme.SUCCESS}]OK[/] {path} [{theme.MUTED}]({time.time()-t0:.1f}s)[/]")


@export.command("csv")
@click.argument("project")
@click.option("--output", "-o", default=None, help="Output file path")
def export_csv_cmd(project, output):
    """Export questions as Anki CSV."""
    t0 = time.time()
    from atenea.export import export_csv
    path = export_csv(project, output_path=output)
    console.print(f"[{theme.SUCCESS}]OK[/] {path} [{theme.MUTED}]({time.time()-t0:.1f}s)[/]")


# ============================================================
# PROJECT MANAGEMENT
# ============================================================

@main.command()
def projects():
    """List all projects."""
    from atenea.storage import list_projects, list_sources, get_project_path, load_json

    project_list = list_projects()
    if not project_list:
        console.print(f"[{theme.MUTED}]No projects. Start with:[/]")
        console.print(f"  atenea sync <project-name>")
        return

    table = Table(title="Projects", border_style=theme.TABLE_BORDER)
    table.add_column("#", style=theme.NAV_OPTION_NUMBER, width=3, justify="right")
    table.add_column("Project", style="bold")
    table.add_column("Sources", justify="right")
    table.add_column("Last sync", style=theme.MUTED)

    for i, p in enumerate(project_list, 1):
        pdata = load_json(str(get_project_path(p, "project.json"))) or {}
        last_sync = pdata.get("last_sync", "never")
        if last_sync != "never":
            last_sync = last_sync[:19].replace("T", " ")
        table.add_row(str(i), p, str(len(list_sources(p))), last_sync)

    console.print(table)


@main.command()
@click.argument("project")
def info(project):
    """Show project info."""
    from atenea.storage import list_sources, get_project_path, load_json

    _location_banner(project, view="info")
    project_data = load_json(str(get_project_path(project, "project.json")))
    if not project_data:
        console.print(f"[{theme.ERROR}]Project '{project}' not found[/]")
        return

    console.print(f"\n[bold]{project}[/bold]")
    console.print(f"[{theme.MUTED}]Created: {project_data.get('created', '?')}[/]")

    if project_data.get("last_sync"):
        console.print(f"[{theme.MUTED}]Last sync: {project_data['last_sync'][:19]}[/]")

    sources = project_data.get("sources", [])
    console.print(f"\nSources: {len(sources)}")
    for s in sources:
        title = s.get("title", s.get("filename", "?"))
        console.print(f"  {s['source_id']}: {title} [{s.get('citekey', '')}]")

    for filename in ["knowledge.json", "questions.json", "coverage.json", "sessions.json", "bibliography.json"]:
        path = get_project_path(project, filename)
        if os.path.exists(str(path)):
            size = os.path.getsize(str(path))
            console.print(f"{filename}: {size:,} bytes")
        else:
            console.print(f"{filename}: [{theme.MUTED}]not created[/]")


# ============================================================
# INIT & DOCTOR
# ============================================================

@main.command()
@click.option("--data-dir", default=None, help="Custom data directory")
def init(data_dir):
    """Initialize Atenea data directory."""
    from pathlib import Path
    from config import defaults
    target = Path(data_dir) if data_dir else Path(defaults.DEFAULT_DATA_DIR)
    target.mkdir(parents=True, exist_ok=True)
    console.print(f"[{theme.SUCCESS}]OK[/] Data directory: {target}")
    console.print(f"Next: atenea sync <project-name>")


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

    for pkg in ["click", "rich", "litellm", "pdfplumber", "fitz", "pyzotero"]:
        try:
            __import__(pkg)
            checks.append((pkg, "installed", True))
        except ImportError:
            checks.append((pkg, "MISSING", False))

    env_vars = {
        "DEEPSEEK_API_KEY": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "ZOTERO_LIBRARY_ID": bool(os.environ.get("ZOTERO_LIBRARY_ID")),
        "ZOTERO_API_KEY": bool(os.environ.get("ZOTERO_API_KEY")),
    }
    for var, present in env_vars.items():
        checks.append((var, "set" if present else "MISSING", present))

    table = Table(title="Doctor", border_style=theme.TABLE_BORDER)
    table.add_column("Check", style="bold")
    table.add_column("Status")
    table.add_column("", justify="center", width=3)
    for name, status, ok in checks:
        icon = f"[{theme.SUCCESS}]{theme.STATUS_ICONS['known']}[/]" if ok else f"[{theme.ERROR}]{theme.STATUS_ICONS['unknown']}[/]"
        table.add_row(name, status, icon)
    console.print(table)


# ============================================================
# HELPERS
# ============================================================

class _spinner:
    """Context manager for a quick spinner."""
    def __init__(self, message):
        self.message = message
        self.progress = Progress(
            SpinnerColumn(theme.PROGRESS_SPINNER),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        )

    def __enter__(self):
        self.progress.start()
        self.task = self.progress.add_task(self.message)
        return self

    def __exit__(self, *args):
        self.progress.stop()


if __name__ == "__main__":
    main()
