"""
atenea/test_engine.py — Interactive Test Engine

Presents questions in the terminal, collects answers, updates coverage.

Pipeline:
1. Select questions (SM-2 priority: due items first, then unknown)
2. Present each question with Rich formatting
3. Collect answer, show result + justification
4. Update coverage.json with SM-2 algorithm
5. Save session to sessions.json
"""

import logging
import random
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from atenea import storage
from config import defaults

log = logging.getLogger(__name__)
console = Console()


# ============================================================
# SM-2 SPACED REPETITION
# ============================================================

def update_sm2(item_data, quality):
    """Update SM-2 parameters for a coverage item.

    Args:
        item_data: dict with ef, interval, reviews, correct
        quality: 0-5 (0=blackout, 5=perfect). ≥3 = passing

    Returns:
        dict: Updated item_data
    """
    ef = item_data.get("ef", defaults.SM2_INITIAL_EF)
    interval = item_data.get("interval", defaults.SM2_INITIAL_INTERVAL_DAYS)
    reviews = item_data.get("reviews", 0)
    correct = item_data.get("correct", 0)

    reviews += 1

    if quality >= defaults.SM2_PASSING_QUALITY:
        correct += 1
        if reviews == 1:
            interval = defaults.SM2_INITIAL_INTERVAL_DAYS
        elif reviews == 2:
            interval = defaults.SM2_SECOND_INTERVAL_DAYS
        else:
            interval = interval * ef
    else:
        # Reset interval on failure
        interval = defaults.SM2_INITIAL_INTERVAL_DAYS

    # Update easiness factor
    ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ef = max(ef, defaults.SM2_EF_MINIMUM)

    # Update status based on performance
    ratio = correct / reviews if reviews > 0 else 0
    if reviews >= 3 and ratio >= 0.8:
        status = "known"
    elif reviews >= 1:
        status = "testing"
    else:
        status = "unknown"

    return {
        "ef": round(ef, 2),
        "interval": round(interval, 1),
        "reviews": reviews,
        "correct": correct,
        "status": status,
        "last": datetime.now(timezone.utc).isoformat(),
    }


# ============================================================
# QUESTION SELECTION
# ============================================================

def select_questions(questions, coverage, n=25):
    """Select questions for a test session.

    Priority:
    1. Questions targeting unknown items
    2. Questions targeting testing items (due for review)
    3. Random from remaining

    Args:
        questions: list of question dicts
        coverage: coverage.json data
        n: number of questions to select

    Returns:
        list[dict]: Selected questions, shuffled
    """
    items = coverage.get("items", {})

    def priority(q):
        targets = q.get("targets", [])
        # Check if any target is unknown
        for t in targets:
            item = items.get(t, {})
            status = item.get("status", "unknown")
            if status == "unknown":
                return 0
            if status == "testing":
                return 1
        return 2

    # Sort by priority, then shuffle within groups
    by_priority = {}
    for q in questions:
        p = priority(q)
        by_priority.setdefault(p, []).append(q)

    selected = []
    for p in [0, 1, 2]:
        group = by_priority.get(p, [])
        random.shuffle(group)
        for q in group:
            if len(selected) >= n:
                break
            selected.append(q)
        if len(selected) >= n:
            break

    random.shuffle(selected)
    return selected


# ============================================================
# QUESTION PRESENTATION
# ============================================================

def present_question(q, idx, total):
    """Display a question in the terminal and collect answer.

    Args:
        q: Question dict
        idx: Current question number (1-based)
        total: Total number of questions

    Returns:
        tuple: (user_answer: str, is_correct: bool)
    """
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

    # Options
    options = q.get("options", {})
    for key in ["A", "B", "C", "D"]:
        if key in options:
            console.print(f"  [bold]{key})[/bold] {options[key]}")

    console.print()

    # Collect answer
    while True:
        try:
            answer = console.input("[yellow]Tu respuesta (A/B/C/D): [/yellow]").strip().upper()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Test interrumpido[/dim]")
            return None, False
        if answer in ["A", "B", "C", "D"]:
            break
        console.print("[red]Respuesta no válida. Usa A, B, C o D.[/red]")

    # Check answer
    correct_answer = q.get("correct", "")
    is_correct = answer == correct_answer

    # Show result
    console.print()
    if is_correct:
        console.print("[bold green]✅ ¡Correcto![/bold green]")
    else:
        console.print(f"[bold red]❌ Incorrecto[/bold red] — "
                      f"La respuesta correcta es [bold]{correct_answer})[/bold] "
                      f"{options.get(correct_answer, '')}")

    # Show justification
    justification = q.get("justification", "")
    if justification:
        console.print()
        console.print(Panel(justification, title="Justificación", border_style="green"))

    console.print("[dim]─" * 50 + "[/dim]")

    return answer, is_correct


# ============================================================
# COVERAGE UPDATE
# ============================================================

def update_coverage(coverage, targets, is_correct):
    """Update coverage.json for the targets of a question.

    Args:
        coverage: Full coverage data dict
        targets: list of target IDs/terms from the question
        is_correct: Whether the user answered correctly
    """
    items = coverage.setdefault("items", {})
    quality = 4 if is_correct else 1  # SM-2 quality score

    for target in targets:
        item_data = items.get(target, {
            "ef": defaults.SM2_INITIAL_EF,
            "interval": defaults.SM2_INITIAL_INTERVAL_DAYS,
            "reviews": 0,
            "correct": 0,
            "status": "unknown",
        })
        items[target] = update_sm2(item_data, quality)


# ============================================================
# SESSION MANAGEMENT
# ============================================================

def write_session(project, results):
    """Save a test session to sessions.json.

    Args:
        project: Project name
        results: list of {question_id, answer, correct, targets}
    """
    sessions_path = str(storage.get_project_path(project, "sessions.json"))
    data = storage.load_json(sessions_path) or {"sessions": []}
    data.setdefault("sessions", [])

    total = len(results)
    correct = sum(1 for r in results if r["correct"])

    session = {
        "date": datetime.now(timezone.utc).isoformat(),
        "total": total,
        "correct": correct,
        "score": round(correct / total * 100, 1) if total > 0 else 0,
        "results": results,
    }

    data["sessions"].append(session)
    storage.save_json(data, sessions_path)
    return session


# ============================================================
# ORCHESTRATOR
# ============================================================

def run_test(project, n=25):
    """Run an interactive test session.

    Args:
        project: Project name
        n: Number of questions

    Returns:
        dict: Session summary
    """
    # Load questions
    questions_path = str(storage.get_project_path(project, "questions.json"))
    q_data = storage.load_json(questions_path)
    if not q_data or not q_data.get("questions"):
        raise ValueError(f"No questions for '{project}'. Run 'atenea generate' first.")

    # Load coverage
    coverage_path = str(storage.get_project_path(project, "coverage.json"))
    coverage = storage.load_json(coverage_path) or {"items": {}}

    # Select questions
    questions = select_questions(q_data["questions"], coverage, n=n)
    if not questions:
        raise ValueError("No questions available for testing.")

    console.print(Panel(
        f"[bold]Test: {project}[/bold]\n"
        f"Preguntas: {len(questions)}\n"
        f"Responde A, B, C o D. Ctrl+C para salir.",
        title="Atenea Test",
        border_style="blue"
    ))

    # Run test
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

    # Save coverage
    coverage["updated"] = storage.now_iso()
    storage.save_json(coverage, coverage_path)

    # Save session
    if results:
        session = write_session(project, results)

        # Show summary
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

    return {"total": 0, "correct": 0, "score": 0}
