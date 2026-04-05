"""
atenea/test_engine.py — Interactive Test Engine (CLI presentation layer)

Thin wrapper over services.test_service that adds Rich terminal display.
All business logic (SM-2, question selection, coverage) lives in test_service.

Pipeline:
1. prepare_test() loads and selects questions
2. present_question() shows each question via tui.select_answer()
3. evaluate_answer() checks correctness
4. update_coverage() applies SM-2
5. finish_test() saves session
"""

import logging

from rich.console import Console
from rich.panel import Panel

from config import defaults
from atenea.services.test_service import (
    prepare_test,
    evaluate_answer,
    update_coverage,
    finish_test,
    build_session_summary,
    get_recent_question_ids,
)

log = logging.getLogger(__name__)
console = Console()


# Re-export pure functions for backward compatibility
from atenea.services.test_service import (  # noqa: F401, E402
    update_sm2,
    select_questions,
    write_session,
)


# ============================================================
# QUESTION PRESENTATION (CLI-only, uses Rich + tui)
# ============================================================

def present_question(q, idx, total):
    """Display a question in the terminal and collect answer.

    Supports 5 options (A-E) with arrow-key, number (1-5), and letter selection.

    Args:
        q: Question dict
        idx: Current question number (1-based)
        total: Total number of questions

    Returns:
        tuple: (user_answer: str, is_correct: bool)
    """
    from atenea.tui import select_answer, divider

    # Header
    console.print()
    console.print(f"[bold blue]Pregunta {idx}/{total}[/bold blue] "
                  f"[dim]({q.get('pattern', 'general')})[/dim]")
    console.print()

    # Context
    if q.get("context"):
        console.print(Panel(q["context"], title="Contexto", border_style="cyan"))

    # Question
    console.print(f"[bold]{q['question']}[/bold]")
    console.print()

    # Collect answer via interactive selector
    options = q.get("options", {})
    answer = select_answer(options)

    if answer is None:
        console.print("\n[dim]Test interrumpido[/dim]")
        return None, False

    # Evaluate
    result = evaluate_answer(q, answer)

    # Show result
    console.print()
    if result["is_correct"]:
        console.print("[bold green]  OK — Correcto[/bold green]")
    else:
        console.print(f"[bold red]  X — Incorrecto[/bold red] — "
                      f"La respuesta correcta es [bold]{result['correct_answer']})[/bold] "
                      f"{result['correct_text']}")

    # Show justification
    if result["justification"]:
        console.print()
        console.print(Panel(result["justification"], title="Justificacion", border_style="green"))

    divider()

    return answer, result["is_correct"]


# ============================================================
# ORCHESTRATOR (CLI wrapper)
# ============================================================

def run_test(project, n=defaults.DEFAULT_QUESTIONS_PER_TEST):
    """Run an interactive test session in the terminal.

    Args:
        project: Project name
        n: Number of questions

    Returns:
        dict: Session summary
    """
    from atenea import storage

    # Prepare test (loads questions + coverage)
    test_data = prepare_test(project, n=n)
    questions = test_data["questions"]
    coverage = test_data["coverage"]

    # Load previous sessions for trend comparison
    sessions_path = str(storage.get_project_path(project, "sessions.json"))
    prev_data = storage.load_json(sessions_path) or {}
    previous_sessions = prev_data.get("sessions", [])

    console.print(Panel(
        f"[bold]Test: {project}[/bold]\n"
        f"Preguntas: {len(questions)}\n"
        f"Responde A-E. Ctrl+C para salir.",
        title="Atenea Test",
        border_style="blue"
    ))

    # Run test loop
    results = []
    for idx, q in enumerate(questions, 1):
        answer, is_correct = present_question(q, idx, len(questions))

        if answer is None:  # User interrupted
            break

        # Record result
        results.append({
            "question_id": q.get("id", ""),
            "answer": answer,
            "correct": is_correct,
            "targets": q.get("targets", []),
        })

        # Update coverage in real-time
        update_coverage(coverage, q.get("targets", []), is_correct)

    # Save coverage + session
    session = finish_test(project, results, coverage)

    # Show verbose summary
    if results and session.get("total", 0) > 0:
        summary = build_session_summary(results, coverage, previous_sessions)
        display_session_summary(summary)

    return session


def display_session_summary(summary):
    """Render a rich post-test summary in the terminal.

    Shows: score + trend, per-concept table, top struggles.

    Args:
        summary: dict from build_session_summary()
    """
    from rich.table import Table

    total = summary["total"]
    correct = summary["correct"]
    score = summary["score"]
    trend = summary["trend"]

    # --- Score + trend header ---
    color = "green" if score >= 70 else "yellow" if score >= 50 else "red"
    bar = f"[{color}]{'█' * int(score / 5)}{'░' * (20 - int(score / 5))}[/{color}]"

    trend_icon = {"up": "[green]↑[/green]", "down": "[red]↓[/red]",
                  "stable": "[yellow]→[/yellow]", "first": "[blue]●[/blue]"}
    t_dir = trend.get("direction", "first")
    t_str = trend_icon.get(t_dir, "●")
    if t_dir in ("up", "down"):
        t_str += f" {trend['delta']:+.0f}%"
    elif t_dir == "stable":
        t_str += " sin cambio"
    else:
        t_str += " primera sesion"

    console.print()
    console.print(Panel(
        f"[bold]Resultado: {correct}/{total} ({score}%)[/bold]  {t_str}\n{bar} {score}%",
        title="Resumen",
        border_style=color,
    ))

    # --- Per-concept table ---
    by_target = summary.get("by_target", [])
    if by_target:
        table = Table(title="Conceptos evaluados", show_lines=False,
                      padding=(0, 1), expand=False)
        table.add_column("Concepto", style="bold", max_width=30)
        table.add_column("Res", justify="center", width=3)
        table.add_column("Estado", justify="center", width=9)
        table.add_column("EF", justify="right", width=5)
        table.add_column("Prox. rev.", justify="right", width=10)

        status_style = {"known": "green", "testing": "yellow", "unknown": "red"}
        status_label = {"known": "dominio", "testing": "estudio", "unknown": "nuevo"}

        for entry in by_target:
            res = "[green]✓[/green]" if entry["correct"] else "[red]✗[/red]"
            st = entry["status"]
            style = status_style.get(st, "dim")
            label = status_label.get(st, st)
            ef = f"{entry['ef']:.2f}"
            days = entry["next_review_days"]
            if days < 1:
                nrev = "<1 dia"
            elif days < 2:
                nrev = "1 dia"
            else:
                nrev = f"{days:.0f} dias"
            table.add_row(entry["term"], res, f"[{style}]{label}[/{style}]", ef, nrev)

        console.print(table)

    # --- Status counts ---
    sc = summary.get("status_counts", {})
    parts = []
    if sc.get("known", 0):
        parts.append(f"[green]{sc['known']} dominio[/green]")
    if sc.get("testing", 0):
        parts.append(f"[yellow]{sc['testing']} estudio[/yellow]")
    if sc.get("unknown", 0):
        parts.append(f"[red]{sc['unknown']} nuevos[/red]")
    if parts:
        console.print(f"  Conceptos: {' | '.join(parts)}")

    # --- Top struggles ---
    struggles = summary.get("top_struggles", [])
    if struggles:
        console.print()
        console.print("[bold red]  Conceptos dificiles:[/bold red]")
        for s in struggles[:5]:
            console.print(f"    [red]▸[/red] {s['term']} — EF {s['ef']:.2f}, "
                          f"{s['ratio']}% correcto en {s['reviews']} intentos")
