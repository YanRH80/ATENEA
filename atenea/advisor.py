"""
atenea/advisor.py — Collection Advisor & Document Summarization

Pre-study analysis module. Provides:
- AI-generated summaries for each document (using SMALL_MODEL)
- Collection-level analysis: topic clusters, study roadmap, scope estimation
- Rich terminal display of advisor reports

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
from atenea.ai import call_llm, call_llm_json, detect_language, get_language_instruction
from atenea.ingest import extract_text
from config import theme
from config.prompts import SUMMARIZE_DOCUMENT_PROMPT, COLLECTION_ADVISOR_PROMPT

console = Console()
log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 4000  # Truncate doc text for summary prompt


def summarize_document(text, metadata, lang="es"):
    """Generate a 2-3 sentence AI summary of a single document.

    Args:
        text: Extracted text from the PDF (will be truncated to MAX_TEXT_CHARS).
        metadata: Bibliography entry dict (needs 'title', 'evidence_level', 'type').
        lang: Language code for prompt instruction.

    Returns:
        str — AI-generated summary.
    """
    prompt = SUMMARIZE_DOCUMENT_PROMPT.format(
        title=metadata.get("title", "Sin titulo"),
        evidence_level=metadata.get("evidence_level", "4"),
        document_type=metadata.get("type", "document"),
        text=text[:MAX_TEXT_CHARS],
        language_instruction=get_language_instruction(lang),
    )
    return call_llm(prompt, task="summary")


def summarize_collection_documents(project, bibliography, on_progress=None):
    """Generate AI summaries for all documents missing one.

    Loads text from text.json for each source. If text.json doesn't exist,
    runs PDF extraction first. Skips entries that already have 'ai_summary'.

    Args:
        project: Project name.
        bibliography: List of bibliography entry dicts.
        on_progress: Optional callback(current, total, message).

    Returns:
        list[dict] — Updated bibliography with 'ai_summary' populated.
    """
    pending = [e for e in bibliography if not e.get("ai_summary") and not e.get("removed")]
    total = len(pending)

    if total == 0:
        return bibliography

    # Detect language from first available text
    sample_lang = "es"

    for i, entry in enumerate(pending):
        source_id = entry.get("source_id")
        title = entry.get("title", "?")

        if on_progress:
            on_progress(i + 1, total, f"Resumiendo: {title[:40]}...")

        if not source_id:
            log.warning(f"Entry sin source_id: {title}")
            continue

        # Load extracted text
        text = _load_source_text(project, source_id)
        if not text:
            log.warning(f"Sin texto extraible para {source_id} ({title})")
            entry["ai_summary"] = "(texto no disponible)"
            continue

        # Detect language on first doc
        if i == 0:
            sample_lang = detect_language(text[:1000])

        try:
            summary = summarize_document(text, entry, lang=sample_lang)
            entry["ai_summary"] = summary
        except Exception as e:
            log.error(f"Error resumiendo {source_id}: {e}")
            entry["ai_summary"] = f"(error: {e})"

    return bibliography


def analyze_collection(bibliography, lang="es"):
    """Analyze a collection and produce a structured study plan.

    Args:
        bibliography: List of bibliography entries (with ai_summary populated).
        lang: Language code.

    Returns:
        dict — Structured analysis with keys:
            collection_profile, topic_clusters, study_roadmap,
            estimated_scope, key_insights
    """
    active = [e for e in bibliography if not e.get("removed")]
    if not active:
        return _empty_report()

    # Build formatted context for the LLM
    lines = []
    for e in active:
        summary = e.get("ai_summary", e.get("abstract", "")[:100])
        lines.append(
            f"- [{e.get('id', '?')}] \"{e.get('title', '?')}\" "
            f"(tipo: {e.get('type', '?')}, evidencia: {e.get('evidence_level', '?')}, "
            f"grado: {e.get('recommendation_grade', '?')})\n"
            f"  Resumen: {summary}"
        )
    collection_summary = "\n".join(lines)

    prompt = COLLECTION_ADVISOR_PROMPT.format(
        collection_summary=collection_summary,
        language_instruction=get_language_instruction(lang),
    )

    return call_llm_json(prompt, task="advisor")


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

    Args:
        project: Project name.
        model: Optional model override.
        skip_summaries: If True, skip AI summary generation.

    Returns:
        dict — The advisor report.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn

    # Load bibliography (handles legacy array and envelope format)
    bibliography = storage.load_bibliography(project)

    if not bibliography:
        console.print(f"[{theme.WARNING}]No hay bibliografia para {project}. Ejecuta sync primero.[/]")
        return _empty_report()

    # Step 1: Generate summaries
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

            # Save updated bibliography with summaries
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


def _load_source_text(project, source_id):
    """Load extracted text for a source, extracting from PDF if needed.

    Returns:
        str — Concatenated text from all pages, or "" if unavailable.
    """
    text_path = storage.get_source_path(project, source_id, "text.json")
    text_data = storage.load_json(str(text_path))

    if text_data and text_data.get("pages"):
        return "\n\n".join(p["text"] for p in text_data["pages"] if p.get("text"))

    # Try to extract from PDF
    pdf_path = storage.get_source_path(project, source_id, "original.pdf")
    if pdf_path.exists():
        log.info(f"Extrayendo texto de {source_id}/original.pdf")
        try:
            pages = extract_text(str(pdf_path))
            # Save for future use
            storage.save_json({"pages": pages}, str(text_path))
            return "\n\n".join(p["text"] for p in pages if p.get("text"))
        except Exception as e:
            log.error(f"Error extrayendo texto de {source_id}: {e}")
            return ""

    return ""


def _empty_report():
    """Return an empty advisor report structure."""
    return {
        "collection_profile": "",
        "topic_clusters": [],
        "study_roadmap": [],
        "estimated_scope": {
            "total_documents": 0,
            "estimated_hours": 0.0,
            "complexity": "N/A",
        },
        "key_insights": [],
    }
