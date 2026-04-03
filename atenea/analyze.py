"""
atenea/analyze.py — Step 6: Learning Analytics

Computes and displays learning analytics from test session history.

Pipeline position:
    [sessions.json + history.json] → analyze.py → analisis.json

== Metrics computed ==

1. Overall mastery: Wilson score across all questions
2. Per-component mastery: Breakdown by CSPOJ component (C, S, P, O, J)
3. Per-path mastery: Which paths are mastered/learning/new
4. Spaced repetition status: Items due for review
5. Session trends: Accuracy over time
6. Weak areas: Components/paths that need the most work
"""

import logging

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from atenea import storage, scoring
from config import defaults

console = Console()
log = logging.getLogger(__name__)


# ============================================================
# ANALYTICS COMPUTATION
# ============================================================

def compute_analytics(project_name):
    """Compute comprehensive learning analytics for a project.

    Args:
        project_name: Project name.

    Returns:
        dict — analytics with overall, per_component, per_path,
               review_status, session_trends, weak_areas.
    """
    history = storage.load_json(
        storage.get_project_path(project_name, "history.json")
    ) or {}

    sessions = storage.load_json(
        storage.get_project_path(project_name, "sessions.json")
    )
    if not isinstance(sessions, list):
        sessions = []

    preguntas = storage.load_json(
        storage.get_project_path(project_name, "preguntas.json")
    ) or {}
    questions = preguntas.get("questions", [])

    # Build question lookup
    q_lookup = {q["id"]: q for q in questions}

    # 1. Overall mastery
    total_correct = sum(h.get("correct_count", 0) for h in history.values())
    total_reviews = sum(h.get("total_count", 0) for h in history.values())
    overall_wilson = scoring.wilson_lower(total_correct, total_reviews)
    overall_level = scoring.mastery_level(total_correct, total_reviews)

    # 2. Per-component mastery
    component_stats = {}
    for qid, h in history.items():
        q = q_lookup.get(qid, {})
        comp = q.get("component", "unknown")
        if comp not in component_stats:
            component_stats[comp] = {"correct": 0, "total": 0}
        component_stats[comp]["correct"] += h.get("correct_count", 0)
        component_stats[comp]["total"] += h.get("total_count", 0)

    per_component = {}
    for comp, stats in component_stats.items():
        wilson = scoring.wilson_lower(stats["correct"], stats["total"])
        per_component[comp] = {
            "correct": stats["correct"],
            "total": stats["total"],
            "wilson_score": round(wilson, 3),
            "level": scoring.mastery_level(stats["correct"], stats["total"]),
            "difficulty": defaults.CSPOJ_COMPONENT_DIFFICULTY.get(comp, 0),
        }

    # 3. Per-path mastery
    path_stats = {}
    for qid, h in history.items():
        q = q_lookup.get(qid, {})
        pid = q.get("path_id", "unknown")
        if pid not in path_stats:
            path_stats[pid] = {"correct": 0, "total": 0}
        path_stats[pid]["correct"] += h.get("correct_count", 0)
        path_stats[pid]["total"] += h.get("total_count", 0)

    per_path = {}
    for pid, stats in path_stats.items():
        wilson = scoring.wilson_lower(stats["correct"], stats["total"])
        per_path[pid] = {
            "correct": stats["correct"],
            "total": stats["total"],
            "wilson_score": round(wilson, 3),
            "level": scoring.mastery_level(stats["correct"], stats["total"]),
        }

    # 4. Review status
    due_count = 0
    critical_count = 0
    for qid, h in history.items():
        days = scoring.days_since(h.get("last_review"))
        interval = h.get("interval", defaults.SM2_INITIAL_INTERVAL_DAYS)
        ret = scoring.retention(days, interval)
        if ret < defaults.RECALL_THRESHOLD:
            due_count += 1
        if ret < defaults.CRITICAL_RETENTION:
            critical_count += 1

    review_status = {
        "total_items": len(history),
        "due_for_review": due_count,
        "critical": critical_count,
        "new_items": len(questions) - len(history),
    }

    # 5. Session trends
    session_trends = []
    for sess in sessions[-10:]:  # Last 10 sessions
        summary = sess.get("summary", {})
        session_trends.append({
            "date": sess.get("date", ""),
            "accuracy": summary.get("accuracy", 0),
            "n_questions": summary.get("total", 0),
            "avg_time_ms": summary.get("avg_response_time_ms", 0),
        })

    # 6. Weak areas
    weak_areas = []
    for comp, stats in per_component.items():
        if stats["total"] > 0 and stats["wilson_score"] < defaults.FAMILIAR_THRESHOLD:
            weak_areas.append({
                "type": "component",
                "name": comp,
                "wilson_score": stats["wilson_score"],
                "total_reviews": stats["total"],
            })

    weak_areas.sort(key=lambda x: x["wilson_score"])

    analytics = {
        "project": project_name,
        "computed_at": storage.now_iso(),
        "overall": {
            "correct": total_correct,
            "total": total_reviews,
            "wilson_score": round(overall_wilson, 3),
            "level": overall_level,
        },
        "per_component": per_component,
        "per_path": per_path,
        "review_status": review_status,
        "session_trends": session_trends,
        "weak_areas": weak_areas,
    }

    # Save
    analytics_path = storage.get_project_path(project_name, "analisis.json")
    storage.save_json(analytics, analytics_path)

    return analytics


# ============================================================
# DISPLAY
# ============================================================

def display_analytics(analytics):
    """Display analytics in the terminal."""
    overall = analytics.get("overall", {})

    # Overall panel
    level_colors = {
        "mastered": "green", "familiar": "yellow",
        "learning": "red", "new": "dim",
    }
    level = overall.get("level", "new")
    color = level_colors.get(level, "white")

    console.print(Panel(
        f"[bold]Overall Mastery:[/bold] [{color}]{level.upper()}[/{color}]\n"
        f"Wilson Score: {overall.get('wilson_score', 0):.3f}\n"
        f"Reviews: {overall.get('correct', 0)}/{overall.get('total', 0)} correct",
        title=f"Project: {analytics.get('project', '?')}",
    ))

    # Component breakdown
    per_comp = analytics.get("per_component", {})
    if per_comp:
        table = Table(title="Mastery by CSPOJ Component")
        table.add_column("Component", style="bold")
        table.add_column("Difficulty", justify="center")
        table.add_column("Correct/Total", justify="right")
        table.add_column("Wilson Score", justify="right")
        table.add_column("Level")

        # Sort by difficulty
        sorted_comps = sorted(per_comp.items(),
                              key=lambda x: x[1].get("difficulty", 0))
        for comp, stats in sorted_comps:
            lvl = stats["level"]
            clr = level_colors.get(lvl, "white")
            table.add_row(
                comp,
                str(stats.get("difficulty", "?")),
                f"{stats['correct']}/{stats['total']}",
                f"{stats['wilson_score']:.3f}",
                f"[{clr}]{lvl}[/{clr}]",
            )
        console.print(table)

    # Review status
    review = analytics.get("review_status", {})
    if review:
        console.print(f"\n[bold]Review Status:[/bold]")
        console.print(f"  Total items tracked: {review.get('total_items', 0)}")
        console.print(f"  Due for review: [yellow]{review.get('due_for_review', 0)}[/yellow]")
        console.print(f"  Critical (R<50%): [red]{review.get('critical', 0)}[/red]")
        console.print(f"  New (never seen): [dim]{review.get('new_items', 0)}[/dim]")

    # Session trends
    trends = analytics.get("session_trends", [])
    if trends:
        table = Table(title="Recent Sessions")
        table.add_column("Date", style="dim")
        table.add_column("Questions", justify="right")
        table.add_column("Accuracy", justify="right")

        for t in trends[-5:]:
            acc = t.get("accuracy", 0)
            acc_color = "green" if acc >= 0.8 else "yellow" if acc >= 0.5 else "red"
            table.add_row(
                t.get("date", "?")[:10],
                str(t.get("n_questions", 0)),
                f"[{acc_color}]{acc:.0%}[/{acc_color}]",
            )
        console.print(table)

    # Weak areas
    weak = analytics.get("weak_areas", [])
    if weak:
        console.print(f"\n[bold red]Weak Areas (need focus):[/bold red]")
        for w in weak[:5]:
            console.print(f"  - {w['name']}: Wilson={w['wilson_score']:.3f} "
                          f"({w['total_reviews']} reviews)")


# ============================================================
# CLI ENTRY POINT
# ============================================================

def run_analytics(project_name):
    """Compute and display analytics for a project.

    Args:
        project_name: Project name.

    Returns:
        dict — analytics data.
    """
    analytics = compute_analytics(project_name)
    display_analytics(analytics)
    console.print(f"\n[dim]Saved to: {storage.get_project_path(project_name, 'analisis.json')}[/dim]")
    return analytics
