"""
atenea/services/test_service.py — Test session logic (UI-agnostic)

Pure functions for:
- SM-2 spaced repetition algorithm
- Question selection by priority
- Answer evaluation
- Coverage tracking
- Session management

No display imports. Returns data structures for any frontend to render.
"""

import random
from datetime import datetime, timezone

from atenea import storage
from config import defaults


# ============================================================
# SM-2 SPACED REPETITION
# ============================================================

def update_sm2(item_data, quality):
    """Update SM-2 parameters for a coverage item.

    Args:
        item_data: dict with ef, interval, reviews, correct
        quality: 0-5 (0=blackout, 5=perfect). >=3 = passing

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
        interval = defaults.SM2_INITIAL_INTERVAL_DAYS

    ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    ef = max(ef, defaults.SM2_EF_MINIMUM)

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
        for t in targets:
            item = items.get(t, {})
            status = item.get("status", "unknown")
            if status == "unknown":
                return 0
            if status == "testing":
                return 1
        return 2

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
    quality = 4 if is_correct else 1

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

    Returns:
        dict: Session summary
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
# HIGH-LEVEL ORCHESTRATION (UI-agnostic)
# ============================================================

def prepare_test(project, n=25):
    """Load questions and coverage, select questions for a test session.

    Args:
        project: Project name
        n: Number of questions

    Returns:
        dict: {"questions": list, "coverage": dict}

    Raises:
        ValueError: If no questions available
    """
    questions_path = str(storage.get_project_path(project, "questions.json"))
    q_data = storage.load_json(questions_path)
    if not q_data or not q_data.get("questions"):
        raise ValueError(f"No questions for '{project}'. Run 'atenea generate' first.")

    coverage_path = str(storage.get_project_path(project, "coverage.json"))
    coverage = storage.load_json(coverage_path) or {"items": {}}

    questions = select_questions(q_data["questions"], coverage, n=n)
    if not questions:
        raise ValueError("No questions available for testing.")

    return {"questions": questions, "coverage": coverage}


def evaluate_answer(question, user_answer):
    """Evaluate a user's answer to a question.

    Args:
        question: Question dict (with 'correct', 'options', 'justification')
        user_answer: User's answer letter (e.g., "A")

    Returns:
        dict: {
            "is_correct": bool,
            "correct_answer": str (letter),
            "correct_text": str (option text),
            "justification": str
        }
    """
    correct_answer = question.get("correct", "")
    options = question.get("options", {})
    is_correct = user_answer == correct_answer

    return {
        "is_correct": is_correct,
        "correct_answer": correct_answer,
        "correct_text": options.get(correct_answer, ""),
        "justification": question.get("justification", ""),
    }


def finish_test(project, results, coverage):
    """Save coverage and session after a test.

    Args:
        project: Project name
        results: list of {question_id, answer, correct, targets}
        coverage: Updated coverage dict

    Returns:
        dict: Session summary with score, or empty dict if no results
    """
    # Save coverage
    coverage_path = str(storage.get_project_path(project, "coverage.json"))
    coverage["updated"] = storage.now_iso()
    storage.save_json(coverage, coverage_path)

    # Save session
    if results:
        return write_session(project, results)

    return {"total": 0, "correct": 0, "score": 0}
