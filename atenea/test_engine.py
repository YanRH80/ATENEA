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

from atenea.services.test_service import (
    prepare_test,
    evaluate_answer,
    update_coverage,
    finish_test,
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

def run_test(project, n=25):
    """Run an interactive test session in the terminal.

    Args:
        project: Project name
        n: Number of questions

    Returns:
        dict: Session summary
    """
    # Prepare test (loads questions + coverage)
    test_data = prepare_test(project, n=n)
    questions = test_data["questions"]
    coverage = test_data["coverage"]

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

    # Show summary
    if results and session.get("total", 0) > 0:
        console.print()
        total = session["total"]
        correct = session["correct"]
        score = session["score"]

        color = "green" if score >= 70 else "yellow" if score >= 50 else "red"
        console.print(Panel(
            f"[bold]Resultado: {correct}/{total} ({score}%)[/bold]\n"
            f"[{color}]{'█' * int(score / 5)}{'░' * (20 - int(score / 5))}[/{color}] {score}%",
            title="Resumen",
            border_style=color
        ))

    return session
