"""
atenea/advisor.py — Collection Advisor (CLI presentation layer)

Thin wrapper over services.advisor_service that adds Rich terminal display.
All LLM logic (summarize, analyze) lives in advisor_service.

This module is for PRE-study analysis. For POST-study coverage tracking,
see review.py.
"""

import logging

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.text import Text

from atenea import storage
from atenea.services.advisor_service import (
    summarize_document,
    summarize_collection_documents,
    analyze_collection,
    run_advisor_pipeline,
    empty_report,
    load_source_text,
)
from atenea.ai import detect_language
from config import theme

console = Console()
log = logging.getLogger(__name__)


def display_advisor_report(report, project):
    """Render the advisor report to terminal using Rich.

    Args:
        report: Dict from analyze_collection().
        project: Project name (for header).
    """
    console.print()

    # 1. Collection profile
    profile = report.get("collection_profile", "")
    if profile:
        console.print(Panel(
            profile,
            title=f"[{theme.HEADER}]{project} — Perfil de coleccion[/]",
            border_style=theme.PANEL_BORDER,
            padding=(1, 2),
        ))

    # 2. Scope summary
    scope = report.get("estimated_scope", {})
    if scope:
        total = scope.get("total_documents", 0)
        hours = scope.get("estimated_hours", 0)
        complexity = scope.get("complexity", "?")
        console.print(
            f"  [{theme.INFO}]Documentos:[/] {total}  "
            f"[{theme.INFO}]Horas estimadas:[/] {hours:.1f}  "
            f"[{theme.INFO}]Complejidad:[/] {complexity}"
        )
        console.print()

    # 3. Topic clusters
    clusters = report.get("topic_clusters", [])
    if clusters:
        table = Table(
            title="Clusters tematicos",
            border_style=theme.TABLE_BORDER,
            show_lines=True,
        )
        table.add_column("#", style=theme.NAV_OPTION_NUMBER, width=3)
        table.add_column("Tema", style=theme.ACCENT, min_width=20)
        table.add_column("Documentos", min_width=15)
        table.add_column("Descripcion", min_width=30)

        for i, cluster in enumerate(clusters, 1):
            docs = ", ".join(cluster.get("documents", []))
            table.add_row(
                str(i),
                cluster.get("topic", ""),
                docs,
                cluster.get("description", ""),
            )
        console.print(table)
        console.print()

    # 4. Study roadmap
    roadmap = report.get("study_roadmap", [])
    if roadmap:
        tree = Tree(
            f"[{theme.HEADER}]Roadmap de estudio[/]",
            guide_style=theme.ACCENT,
        )
        for item in roadmap:
            order = item.get("order", "?")
            title = item.get("title", "?")
            rationale = item.get("rationale", "")
            node = tree.add(
                f"[{theme.NAV_OPTION_NUMBER}]{order}.[/] {title}"
            )
            if rationale:
                node.add(f"[{theme.MUTED}]{rationale}[/]")
        console.print(tree)
        console.print()

    # 5. Key insights
    insights = report.get("key_insights", [])
    if insights:
        text = Text()
        for insight in insights:
            text.append("  • ", style=theme.ACCENT)
            text.append(f"{insight}\n")
        console.print(Panel(
            text,
            title=f"[{theme.HEADER}]Insights clave[/]",
            border_style=theme.PANEL_BORDER,
        ))


def run_advisor(project, model=None, skip_summaries=False):
    """Orchestrate full advisor workflow: summarize + analyze + display.

    CLI wrapper that adds Rich progress bars and display over advisor_service.

    Args:
        project: Project name.
        model: Optional model override.
        skip_summaries: If True, skip AI summary generation.

    Returns:
        dict — The advisor report.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn

    bibliography = storage.load_bibliography(project)

    if not bibliography:
        console.print(f"[{theme.WARNING}]No hay bibliografia para {project}. Ejecuta sync primero.[/]")
        return empty_report()

    # Step 1: Generate summaries with Rich progress
    if not skip_summaries:
        pending_count = sum(1 for e in bibliography if not e.get("ai_summary") and not e.get("removed"))
        if pending_count > 0:
            console.print(f"[{theme.INFO}]Generando resumenes AI para {pending_count} documentos...[/]")
            with Progress(
                SpinnerColumn(style=theme.PROGRESS_BAR_STYLE),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Resumiendo...", total=pending_count)

                def on_progress(current, total, message):
                    progress.update(task, completed=current, description=message)

                bibliography = summarize_collection_documents(project, bibliography, on_progress)

            storage.save_bibliography(project, bibliography)
            console.print(f"[{theme.SUCCESS}]Resumenes generados y guardados.[/]")

    # Step 2: Analyze collection
    console.print(f"[{theme.INFO}]Analizando coleccion...[/]")
    lang = detect_language(
        " ".join(e.get("ai_summary", "") for e in bibliography if e.get("ai_summary"))[:2000]
        or "es"
    )
    report = analyze_collection(bibliography, lang=lang)

    # Save advisor report
    advisor_path = storage.get_project_path(project, "advisor.json")
    storage.save_json(report, str(advisor_path))

    # Step 3: Display
    display_advisor_report(report, project)

    return report
