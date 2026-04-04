"""
atenea/review.py — Coverage Analysis & Gap Detection

Computes coverage statistics and identifies knowledge gaps:
- Per-type coverage (keywords, associations, sequences)
- Per-source coverage
- Weak areas (repeatedly failed items)
- Suggested refinements via LLM (optional)

Pipeline: coverage.json + knowledge.json → terminal display + updated coverage
"""

import logging

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from atenea import ai, storage
from config import prompts

log = logging.getLogger(__name__)
console = Console()


# ============================================================
# COVERAGE COMPUTATION
# ============================================================

def compute_coverage(project):
    """Compute coverage statistics from knowledge.json + coverage.json.

    Returns:
        dict with summary stats and per-source breakdown.
    """
    knowledge_path = str(storage.get_project_path(project, "knowledge.json"))
    coverage_path = str(storage.get_project_path(project, "coverage.json"))

    knowledge = storage.load_json(knowledge_path)
    coverage = storage.load_json(coverage_path) or {"items": {}}
    items = coverage.get("items", {})

    summary = {}
    by_source = {}

    for item_type in ["keywords", "associations", "sequences"]:
        type_items = knowledge.get(item_type, [])
        total = len(type_items)
        known = testing = unknown = 0

        for item in type_items:
            # Check coverage by term (keywords) or id
            key = item.get("term", item.get("id", ""))
            status = items.get(key, {}).get("status", "unknown")

            if status == "known":
                known += 1
            elif status == "testing":
                testing += 1
            else:
                unknown += 1

            # Per-source tracking
            source = item.get("source", "unknown")
            src_data = by_source.setdefault(source, {
                "total": 0, "known": 0, "testing": 0, "unknown": 0
            })
            src_data["total"] += 1
            src_data[status if status in ("known", "testing") else "unknown"] += 1

        summary[item_type] = {
            "total": total,
            "known": known,
            "testing": testing,
            "unknown": unknown,
        }

    return {"summary": summary, "by_source": by_source}


# ============================================================
# GAP DETECTION
# ============================================================

def detect_gaps(project):
    """Identify weak areas from coverage data.

    Returns items that have been reviewed but have low success rates.
    """
    coverage_path = str(storage.get_project_path(project, "coverage.json"))
    coverage = storage.load_json(coverage_path) or {"items": {}}
    items = coverage.get("items", {})

    gaps = []
    for term, data in items.items():
        reviews = data.get("reviews", 0)
        correct = data.get("correct", 0)
        if reviews >= 2 and correct / reviews < 0.5:
            gaps.append({
                "term": term,
                "reviews": reviews,
                "correct": correct,
                "ratio": round(correct / reviews * 100, 1),
                "ef": data.get("ef", 0),
            })

    # Sort by worst performance
    gaps.sort(key=lambda x: x["ratio"])
    return gaps


# ============================================================
# DISPLAY
# ============================================================

def display_coverage(project):
    """Display coverage statistics in the terminal."""
    stats = compute_coverage(project)
    summary = stats["summary"]
    by_source = stats["by_source"]

    # Header
    console.print()
    console.print(Panel(f"[bold]COBERTURA: {project}[/bold]", border_style="blue"))

    # Main table
    table = Table()
    table.add_column("", style="bold")
    table.add_column("Total", justify="right")
    table.add_column("Visto", justify="right")
    table.add_column("Dominio", justify="right")

    for item_type, data in summary.items():
        total = data["total"]
        seen = data["known"] + data["testing"]
        seen_pct = round(seen / total * 100) if total > 0 else 0
        known = data["known"]
        known_pct = round(known / total * 100) if total > 0 else 0

        label = {
            "keywords": "Keywords",
            "associations": "Asociaciones",
            "sequences": "Secuencias",
        }.get(item_type, item_type)

        table.add_row(
            label,
            str(total),
            f"{seen} ({seen_pct}%)",
            f"{known} ({known_pct}%)",
        )

    console.print(table)

    # Overall progress bar
    all_total = sum(d["total"] for d in summary.values())
    all_seen = sum(d["known"] + d["testing"] for d in summary.values())
    all_known = sum(d["known"] for d in summary.values())

    if all_total > 0:
        seen_pct = round(all_seen / all_total * 100)
        known_pct = round(all_known / all_total * 100)
        console.print()
        console.print(f"  {'█' * (seen_pct // 5)}{'░' * (20 - seen_pct // 5)}  "
                      f"{seen_pct}% visto")
        console.print(f"  {'█' * (known_pct // 5)}{'░' * (20 - known_pct // 5)}  "
                      f"{known_pct}% dominado")

    # Per-source breakdown
    if by_source:
        console.print()
        console.print("[bold]Por fuente:[/bold]")
        for source, data in by_source.items():
            total = data["total"]
            seen = data["known"] + data["testing"]
            pct = round(seen / total * 100) if total > 0 else 0
            bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
            console.print(f"  {source}  {bar} {pct}%")

    console.print()


def display_gaps(project):
    """Display knowledge gaps in the terminal."""
    gaps = detect_gaps(project)

    if not gaps:
        console.print("[green]No hay lagunas significativas detectadas.[/green]")
        return

    console.print()
    console.print(Panel("[bold]LAGUNAS DE CONOCIMIENTO[/bold]", border_style="red"))

    table = Table()
    table.add_column("Concepto", style="bold")
    table.add_column("Intentos", justify="right")
    table.add_column("Aciertos", justify="right")
    table.add_column("Ratio", justify="right")
    table.add_column("EF", justify="right")

    for gap in gaps[:15]:  # Top 15 worst
        color = "red" if gap["ratio"] < 30 else "yellow"
        table.add_row(
            gap["term"][:40],
            str(gap["reviews"]),
            str(gap["correct"]),
            f"[{color}]{gap['ratio']}%[/{color}]",
            str(gap["ef"]),
        )

    console.print(table)
    console.print()


# ============================================================
# ORCHESTRATOR
# ============================================================

def run_review(project, use_llm=False, model=None):
    """Run a full review: coverage stats + gaps + optional LLM analysis.

    Args:
        project: Project name
        use_llm: Whether to use LLM for gap analysis suggestions
        model: LLM model override
    """
    display_coverage(project)
    display_gaps(project)

    if use_llm:
        console.print("[dim]Analizando gaps con LLM...[/dim]")
        gaps = detect_gaps(project)
        if gaps:
            knowledge_path = str(storage.get_project_path(project, "knowledge.json"))
            knowledge = storage.load_json(knowledge_path)

            # Build context
            gap_text = "\n".join(
                f"- {g['term']}: {g['correct']}/{g['reviews']} ({g['ratio']}%)"
                for g in gaps[:10]
            )
            kw_text = "\n".join(
                f"- {kw['term']}: {kw.get('definition', '')[:60]}"
                for kw in knowledge.get("keywords", [])[:20]
            )

            lang = ai.detect_language(kw_text[:500])
            prompt = prompts.ANALYZE_GAPS_PROMPT.format(
                session_results=gap_text,
                knowledge_summary=kw_text,
                language_instruction=ai.get_language_instruction(lang),
            )

            result = ai.call_llm_json(prompt, model=model, task="evaluation")
            if result:
                console.print()
                console.print(Panel("[bold]Sugerencias del LLM[/bold]", border_style="yellow"))
                for area in result.get("weak_areas", []):
                    console.print(f"  [red]⚠[/red] {area}")
                focus = result.get("suggested_focus", "")
                if focus:
                    console.print(f"\n  [bold]Prioridad:[/bold] {focus}")
