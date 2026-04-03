"""
atenea/test_engine.py — Step 5: Adaptive Test Engine

Runs interactive test sessions using questions from preguntas.json.
Adapts question selection based on spaced repetition and priority.

Pipeline position:
    [preguntas.json] → test_engine.py → analisis.json → [analyze.py]

== How adaptive selection works ==

1. Load all questions and their review history
2. Score each question by priority (see scoring.py)
3. Select the top-N by priority, with interleaving bonus
4. Present questions, evaluate answers, update scores
5. Save results to session history

== Session data structure ==

Each session produces a record in analisis.json with:
- Session metadata (date, duration, n_questions)
- Per-question results (answer, score, response_time, quality)
- Updated SM-2 parameters for each path/component
"""

import json
import time
import logging

from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel
from rich.table import Table

from atenea import ai, storage, scoring
from atenea.utils import generate_id
from config import defaults

console = Console()
log = logging.getLogger(__name__)


# ============================================================
# QUESTION SELECTION (ADAPTIVE)
# ============================================================

def select_questions(questions, history, n=None):
    """Select questions for a test session using adaptive priority.

    Prioritizes questions the student needs most, based on:
    - SM-2 schedule (overdue items first)
    - Ebbinghaus retention (about-to-forget items)
    - Performance history (weak areas)
    - Interleaving (mix contexts)

    Args:
        questions: List of all question dicts from preguntas.json.
        history: Dict mapping question_id → review history.
        n: Number of questions to select. Default from config.

    Returns:
        list[dict] — selected questions ordered by priority.
    """
    n = n or defaults.DEFAULT_QUESTIONS_PER_TEST

    scored = []
    recent_contexts = []
    for q in questions:
        qid = q["id"]
        h = history.get(qid, {})

        # Get review history stats
        correct = h.get("correct_count", 0)
        total = h.get("total_count", 0)
        last_review = h.get("last_review", None)
        ef = h.get("ef", defaults.SM2_INITIAL_EF)
        interval = h.get("interval", defaults.SM2_INITIAL_INTERVAL_DAYS)
        qualities = h.get("qualities", [])

        # Compute factors
        days = scoring.days_since(last_review)
        ret = scoring.retention(days, interval)
        consistency = scoring.compute_consistency(qualities)
        mastery = scoring.wilson_lower(correct, total)
        is_new = total == 0

        # Priority (simplified: centrality=difficulty/5, connected_mastery=0.5)
        priority = scoring.compute_priority(
            path_score_val=mastery,
            connected_mastery=0.5,  # Will be refined with graph analysis
            centrality=q.get("difficulty", 1) / 5.0,
            retention_val=ret,
            recent_contexts=recent_contexts,
            is_new=is_new,
        )

        scored.append((priority, q))

    # Sort by priority (highest first)
    scored.sort(key=lambda x: x[0], reverse=True)

    # Apply new-item ratio cap and track contexts for interleaving
    selected = []
    new_count = 0
    max_new = int(n * defaults.MAX_NEW_ITEM_RATIO)
    selected_contexts = []

    for priority, q in scored:
        if len(selected) >= n:
            break
        qid = q["id"]
        h = history.get(qid, {})
        is_new = h.get("total_count", 0) == 0

        if is_new:
            if new_count >= max_new:
                continue
            new_count += 1

        selected.append(q)
        # Track context for interleaving in future sessions
        ctx = q.get("question_text", "") or q.get("statement", "")
        selected_contexts.append(ctx[:50])

    return selected


# ============================================================
# ANSWER EVALUATION
# ============================================================

def evaluate_answer(question, user_answer, model=None):
    """Evaluate a user's answer to a question.

    For True/False and Multiple Choice: exact match.
    For Free Text: LLM-based semantic evaluation.

    Args:
        question: Question dict.
        user_answer: String with the user's answer.
        model: Override model for LLM evaluation.

    Returns:
        dict — result with: is_correct, is_partial, score, feedback
    """
    qtype = question["type"]

    if qtype == "true_false":
        return _evaluate_tf(question, user_answer)
    elif qtype == "multiple_choice":
        return _evaluate_mc(question, user_answer)
    elif qtype == "free_text":
        return _evaluate_free_text(question, user_answer, model=model)
    else:
        return {"is_correct": False, "is_partial": False, "score": 0.0,
                "feedback": "Unknown question type"}


def _evaluate_tf(question, user_answer):
    """Evaluate a True/False answer."""
    answer_normalized = user_answer.strip().lower()
    true_answers = {"true", "verdadero", "v", "t", "si", "sí", "1"}
    false_answers = {"false", "falso", "f", "no", "0"}

    user_said_true = answer_normalized in true_answers
    user_said_false = answer_normalized in false_answers

    if not user_said_true and not user_said_false:
        return {
            "is_correct": False, "is_partial": False, "score": 0.0,
            "feedback": "Responde 'Verdadero' o 'Falso'",
        }

    is_correct = (user_said_true == question["is_true"])
    return {
        "is_correct": is_correct,
        "is_partial": False,
        "score": 1.0 if is_correct else 0.0,
        "feedback": question.get("explanation", ""),
    }


def _evaluate_mc(question, user_answer):
    """Evaluate a Multiple Choice answer."""
    answer = user_answer.strip()

    # Accept index (1-based) or letter (a, b, c, d)
    correct_idx = question["correct_index"]
    options = question.get("options", [])

    user_idx = None
    if answer.isdigit():
        user_idx = int(answer) - 1  # Convert to 0-based
    elif len(answer) == 1 and answer.lower() in "abcdefgh":
        user_idx = ord(answer.lower()) - ord("a")
    else:
        # Try matching the text directly
        for i, opt in enumerate(options):
            if answer.lower() == opt.lower():
                user_idx = i
                break

    if user_idx is None or user_idx < 0 or user_idx >= len(options):
        return {
            "is_correct": False, "is_partial": False, "score": 0.0,
            "feedback": f"Opción no válida. Elige 1-{len(options)} o a-{chr(ord('a') + len(options) - 1)}",
        }

    is_correct = user_idx == correct_idx
    return {
        "is_correct": is_correct,
        "is_partial": False,
        "score": 1.0 if is_correct else 0.0,
        "feedback": question.get("explanation", "") if not is_correct else "",
    }


def _evaluate_free_text(question, user_answer, model=None):
    """Evaluate a Free Text answer using LLM."""
    correct = question["correct_answer"]
    justification = question.get("explanation", "")

    # Quick exact/near match check first
    if user_answer.strip().lower() == correct.strip().lower():
        return {"is_correct": True, "is_partial": False, "score": 1.0, "feedback": ""}

    # LLM evaluation
    lang_instruction = ai.get_language_instruction("es")  # TODO: detect from question
    from config.prompts import EVALUATE_ANSWER_PROMPT
    prompt = EVALUATE_ANSWER_PROMPT.format(
        question=question["question_text"],
        expected=correct,
        justification=justification,
        user_answer=user_answer,
        language_instruction=lang_instruction,
    )

    try:
        result = ai.call_llm_json(prompt, model=model, task="evaluation")
        score = float(result.get("score", 0.0))
        return {
            "is_correct": result.get("correct", score >= 0.8),
            "is_partial": 0.3 < score < 0.8,
            "score": score,
            "feedback": result.get("feedback", ""),
        }
    except Exception as e:
        log.warning(f"LLM evaluation failed: {e}")
        # Fallback: simple substring match
        if correct.lower()[:20] in user_answer.lower():
            return {"is_correct": False, "is_partial": True, "score": 0.5,
                    "feedback": "Evaluación aproximada (LLM no disponible)"}
        return {"is_correct": False, "is_partial": False, "score": 0.0,
                "feedback": f"Respuesta esperada: {correct}"}


# ============================================================
# TEST SESSION
# ============================================================

def run_test(project_name, source_id=None, n_questions=None, model=None):
    """Run an interactive adaptive test session.

    This is the main entry point for Step 5. It:
    1. Loads questions and history
    2. Selects questions adaptively
    3. Presents each question interactively
    4. Evaluates answers and updates scores
    5. Saves session results

    Args:
        project_name: Project name.
        source_id: Source ID (None for latest).
        n_questions: Number of questions (None for config default).
        model: Override model for evaluation.

    Returns:
        dict — session results.
    """
    # Load questions
    if source_id is None:
        sources = storage.list_sources(project_name)
        if not sources:
            raise FileNotFoundError(f"No sources in project '{project_name}'")
        source_id = sources[-1]

    preguntas_path = storage.get_source_path(project_name, source_id, "preguntas.json")
    preguntas = storage.load_json(preguntas_path)
    if not preguntas:
        raise FileNotFoundError(f"No preguntas.json for {source_id}. Run 'atenea generate' first.")

    questions = preguntas.get("questions", [])
    if not questions:
        console.print("[yellow]No questions available[/yellow]")
        return {}

    # Load history
    history = _load_history(project_name)

    # Select questions
    n = n_questions or defaults.DEFAULT_QUESTIONS_PER_TEST
    n = min(n, len(questions))
    selected = select_questions(questions, history, n=n)

    console.print(Panel(
        f"[bold]Test Session[/bold]\n"
        f"Project: {project_name}\n"
        f"Questions: {len(selected)} / {len(questions)} available\n"
        f"Type 'q' to quit early",
        title="Atenea Test",
    ))

    # Run session
    session_id = generate_id("sess")
    results = []
    start_time = time.time()

    for i, question in enumerate(selected, 1):
        console.print(f"\n[bold]Question {i}/{len(selected)}[/bold] "
                       f"[dim](diff: {question.get('difficulty', '?')}, "
                       f"component: {question.get('component', '?')})[/dim]")

        # Display question
        _display_question(question, i)

        # Get answer
        q_start = time.time()
        user_answer = Prompt.ask("[bold cyan]Tu respuesta[/bold cyan]")
        q_elapsed_ms = int((time.time() - q_start) * 1000)

        if user_answer.strip().lower() == "q":
            console.print("[dim]Test ended early[/dim]")
            break

        # Evaluate
        eval_result = evaluate_answer(question, user_answer, model=model)

        # Infer SM-2 quality
        quality = scoring.infer_quality(
            eval_result["is_correct"],
            eval_result["is_partial"],
            q_elapsed_ms,
        )

        # Display feedback
        _display_feedback(eval_result, question)

        # Record result
        results.append({
            "question_id": question["id"],
            "path_id": question.get("path_id"),
            "component": question.get("component"),
            "user_answer": user_answer,
            "is_correct": eval_result["is_correct"],
            "is_partial": eval_result["is_partial"],
            "score": eval_result["score"],
            "quality": quality,
            "response_time_ms": q_elapsed_ms,
        })

        # Update history
        _update_history(history, question["id"], eval_result, quality)

    # Session summary
    elapsed = time.time() - start_time
    session = {
        "session_id": session_id,
        "project": project_name,
        "source_id": source_id,
        "date": storage.now_iso(),
        "duration_seconds": round(elapsed),
        "n_questions": len(results),
        "results": results,
        "summary": _session_summary(results),
    }

    # Save
    _save_history(project_name, history)
    _save_session(project_name, session)
    _display_session_summary(session["summary"])

    return session


# ============================================================
# DISPLAY HELPERS
# ============================================================

def _display_question(question, number):
    """Display a question in the terminal."""
    qtype = question["type"]

    if qtype == "true_false":
        console.print(f"[bold]¿Verdadero o Falso?[/bold]")
        console.print(f"  {question['statement']}")

    elif qtype == "multiple_choice":
        console.print(f"  {question['question_text']}")
        for i, opt in enumerate(question.get("options", [])):
            letter = chr(ord("a") + i)
            console.print(f"  [bold]{letter})[/bold] {opt}")

    elif qtype == "free_text":
        console.print(f"  {question['question_text']}")


def _display_feedback(eval_result, question):
    """Display evaluation feedback."""
    score = eval_result["score"]

    if eval_result["is_correct"]:
        console.print(f"  [green bold]✓ Correcto[/green bold] ({score:.0%})")
    elif eval_result["is_partial"]:
        console.print(f"  [yellow bold]~ Parcialmente correcto[/yellow bold] ({score:.0%})")
    else:
        console.print(f"  [red bold]✗ Incorrecto[/red bold]")
        correct = question.get("correct_answer", "")
        if correct:
            console.print(f"  [dim]Respuesta correcta: {correct[:100]}[/dim]")

    feedback = eval_result.get("feedback", "")
    if feedback and not eval_result["is_correct"]:
        console.print(f"  [dim]{feedback[:150]}[/dim]")


def _display_session_summary(summary):
    """Display end-of-session summary."""
    console.print("\n")
    table = Table(title="Session Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Questions answered", str(summary["total"]))
    table.add_row("Correct", f"[green]{summary['correct']}[/green]")
    table.add_row("Partial", f"[yellow]{summary['partial']}[/yellow]")
    table.add_row("Incorrect", f"[red]{summary['incorrect']}[/red]")
    table.add_row("Accuracy", f"{summary['accuracy']:.0%}")
    table.add_row("Avg response time", f"{summary['avg_response_time_ms']:.0f}ms")

    console.print(table)


# ============================================================
# HISTORY & SESSION PERSISTENCE
# ============================================================

def _load_history(project_name):
    """Load question review history for a project."""
    path = storage.get_project_path(project_name, "history.json")
    return storage.load_json(path) or {}


def _save_history(project_name, history):
    """Save question review history."""
    path = storage.get_project_path(project_name, "history.json")
    storage.save_json(history, path)


def _update_history(history, question_id, eval_result, quality):
    """Update history for a single question after answering."""
    h = history.get(question_id, {
        "correct_count": 0,
        "total_count": 0,
        "ef": defaults.SM2_INITIAL_EF,
        "interval": defaults.SM2_INITIAL_INTERVAL_DAYS,
        "repetition": 0,
        "last_review": None,
        "qualities": [],
    })

    h["total_count"] += 1
    if eval_result["is_correct"]:
        h["correct_count"] += 1

    # Update SM-2
    h["ef"], h["interval"], h["repetition"] = scoring.update_sm2(
        h["ef"], h["interval"], h["repetition"], quality,
    )
    h["last_review"] = storage.now_iso()
    h["qualities"].append(quality)

    history[question_id] = h


def _save_session(project_name, session):
    """Append a session to the sessions log."""
    path = storage.get_project_path(project_name, "sessions.json")
    sessions = storage.load_json(path)
    if not isinstance(sessions, list):
        sessions = []
    sessions.append(session)
    storage.save_json(sessions, path)


def _session_summary(results):
    """Compute summary stats for a session."""
    total = len(results)
    if total == 0:
        return {"total": 0, "correct": 0, "partial": 0, "incorrect": 0,
                "accuracy": 0.0, "avg_response_time_ms": 0}

    correct = sum(1 for r in results if r["is_correct"])
    partial = sum(1 for r in results if r["is_partial"])
    incorrect = total - correct - partial
    avg_time = sum(r["response_time_ms"] for r in results) / total

    return {
        "total": total,
        "correct": correct,
        "partial": partial,
        "incorrect": incorrect,
        "accuracy": correct / total,
        "avg_response_time_ms": avg_time,
    }
