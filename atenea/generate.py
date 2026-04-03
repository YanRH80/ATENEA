"""
atenea/generate.py — Step 4: Question Generation from CSPOJ

Generates questions from CSPOJ pentads in data.json. Three question types:

1. True/False: Alter one CSPOJ component to create a plausible false statement
2. Multiple Choice: Correct answer + LLM-generated distractors
3. Free Text: Hide one CSPOJ component, student provides it

Pipeline position:
    [data.json] → generate.py → preguntas.json → [test_engine.py]

== Question generation strategy ==

Each CSPOJ path can generate multiple questions by hiding different components:
- Hide Object → "¿Qué produce la mitocondria?" (easiest)
- Hide Subject → "¿Qué organelo produce ATP?"
- Hide Predicate → "¿Qué relación tiene la mitocondria con el ATP?"
- Hide Justification → "¿Por qué la mitocondria produce ATP?"
- Hide Context → "¿En qué campo se estudia la producción de ATP?" (hardest)

Difficulty follows CSPOJ_COMPONENT_DIFFICULTY from config/defaults.py.
"""

import json
import logging
import random

from rich.console import Console
from rich.progress import Progress

from atenea import ai, storage
from atenea.utils import generate_id
from config import defaults, prompts, models as models_config

console = Console()
log = logging.getLogger(__name__)

# Question types
Q_TRUE_FALSE = "true_false"
Q_MULTIPLE_CHOICE = "multiple_choice"
Q_FREE_TEXT = "free_text"

# CSPOJ components that can be hidden (in difficulty order)
HIDEABLE_COMPONENTS = ["object", "subject", "predicate", "justification", "context"]


# ============================================================
# TRUE/FALSE GENERATION
# ============================================================

def generate_true_false(path, component, model=None, temperature=None, lang="es"):
    """Generate a True/False question by altering a CSPOJ component.

    The LLM creates a plausible but FALSE statement by modifying
    one component of the original CSPOJ path.

    Args:
        path: CSPOJ path dict with context, subject, predicate, object, justification.
        component: Which component to alter ("subject", "object", "predicate", etc.).
        model: Override model.
        temperature: Override temperature.
        lang: Language code ("es" or "en").

    Returns:
        dict — question with: id, type, path_id, component, statement,
               is_true, correct_answer, explanation, difficulty, bloom_level
    """
    lang_instruction = ai.get_language_instruction(lang)

    prompt = prompts.GENERATE_TF_PROMPT.format(
        context=path['context'],
        subject=path['subject'],
        predicate=path['predicate'],
        object=path['object'],
        justification=path['justification'],
        component=component,
        language_instruction=lang_instruction,
    )

    try:
        result = ai.call_llm_json(
            prompt, model=model, temperature=temperature,
            task="question_gen_tf",
        )
    except Exception as e:
        log.warning(f"T/F generation failed for path {path['id']}: {e}")
        return None

    if not isinstance(result, dict):
        return None

    difficulty = defaults.CSPOJ_COMPONENT_DIFFICULTY.get(component, 1)

    # Generate both true and false versions
    false_question = {
        "id": generate_id("q"),
        "type": Q_TRUE_FALSE,
        "path_id": path["id"],
        "component": component,
        "statement": result.get("statement", ""),
        "is_true": False,
        "correct_answer": "Falso" if lang == "es" else "False",
        "explanation": result.get("why_false", ""),
        "difficulty": difficulty,
        "bloom_level": 1,  # Remember
    }

    # Also create a true version using the original path
    true_statement = _build_true_statement(path, lang)
    true_question = {
        "id": generate_id("q"),
        "type": Q_TRUE_FALSE,
        "path_id": path["id"],
        "component": component,
        "statement": true_statement,
        "is_true": True,
        "correct_answer": "Verdadero" if lang == "es" else "True",
        "explanation": path.get("justification", ""),
        "difficulty": difficulty,
        "bloom_level": 1,
    }

    return [false_question, true_question]


def _build_true_statement(path, lang):
    """Build a true statement from a CSPOJ path.

    Assembles a natural-sounding statement from the components.

    Args:
        path: CSPOJ path dict.
        lang: Language code.

    Returns:
        str — true statement.
    """
    s = path["subject"]
    p = path["predicate"]
    o = path["object"]
    c = path["context"]

    if lang == "es":
        return f"En el contexto de {c}, {s} {p} {o}."
    else:
        return f"In the context of {c}, {s} {p} {o}."


# ============================================================
# MULTIPLE CHOICE GENERATION
# ============================================================

def generate_multiple_choice(path, component, model=None, temperature=None,
                             lang="es", n_distractors=3):
    """Generate a Multiple Choice question from a CSPOJ path.

    Hides one component (the correct answer) and asks the LLM
    to generate plausible distractors.

    Args:
        path: CSPOJ path dict.
        component: Which component to hide and ask about.
        model: Override model.
        temperature: Override temperature.
        lang: Language code.
        n_distractors: Number of incorrect options to generate.

    Returns:
        dict — question with: id, type, path_id, component, question_text,
               options, correct_index, explanation, difficulty, bloom_level
    """
    correct_answer = path.get(component, "")
    if not correct_answer:
        return None

    question_text = _build_question_text(path, component, lang)
    lang_instruction = ai.get_language_instruction(lang)

    # Gather related concepts from the path for distractor context
    related_concepts = ", ".join(
        v for k, v in path.items()
        if k in ("context", "subject", "object") and v and v != correct_answer
    )

    prompt = prompts.GENERATE_MC_PROMPT.format(
        question=question_text,
        correct_answer=correct_answer,
        n_distractors=n_distractors,
        related_concepts=related_concepts,
        language_instruction=lang_instruction,
    )

    try:
        result = ai.call_llm_json(
            prompt, model=model, temperature=temperature,
            task="question_gen_mc",
        )
    except Exception as e:
        log.warning(f"MC generation failed for path {path['id']}: {e}")
        return None

    # Robust parsing: handle dict, list, or nested formats
    distractors = _extract_distractors(result)

    if not distractors:
        log.warning(f"MC: no distractors parsed for path {path['id']}, raw={type(result).__name__}")
        return None

    # Accept 2+ distractors (3 is ideal but 2 is still a valid MC question)
    if len(distractors) < 2:
        log.warning(f"MC: only {len(distractors)} distractors for path {path['id']}")
        return None

    # Validate distractors
    distractors = validate_distractors(correct_answer, distractors)
    if len(distractors) < 2:
        return None

    # Build options: correct answer + distractors, shuffled
    options = [correct_answer] + distractors[:n_distractors]
    random.shuffle(options)
    correct_index = options.index(correct_answer)

    difficulty = defaults.CSPOJ_COMPONENT_DIFFICULTY.get(component, 1)

    return {
        "id": generate_id("q"),
        "type": Q_MULTIPLE_CHOICE,
        "path_id": path["id"],
        "component": component,
        "question_text": question_text,
        "options": options,
        "correct_index": correct_index,
        "correct_answer": correct_answer,
        "explanation": path.get("justification", ""),
        "difficulty": difficulty,
        "bloom_level": 2,  # Understand
        "n_options": len(options),
    }


def _extract_distractors(result):
    """Robustly extract a list of distractor strings from LLM output.

    Handles multiple formats the LLM might return:
    - {"distractors": ["a", "b", "c"]}     (expected)
    - ["a", "b", "c"]                        (plain array)
    - {"options": ["a", "b", "c"]}           (alternate key)
    - [{"text": "a"}, {"text": "b"}]         (list of dicts)
    """
    if isinstance(result, dict):
        # Try common keys
        for key in ("distractors", "options", "incorrect_options", "choices"):
            if key in result and isinstance(result[key], list):
                return _flatten_to_strings(result[key])
        # If dict has a single list value, use it
        for v in result.values():
            if isinstance(v, list):
                return _flatten_to_strings(v)
        return []

    if isinstance(result, list):
        return _flatten_to_strings(result)

    return []


def _flatten_to_strings(items):
    """Convert a list of mixed items to a list of strings."""
    strings = []
    for item in items:
        if isinstance(item, str) and item.strip():
            strings.append(item.strip())
        elif isinstance(item, dict):
            # Try common keys
            for key in ("text", "option", "distractor", "value"):
                if key in item and isinstance(item[key], str):
                    strings.append(item[key].strip())
                    break
    return strings


def validate_distractors(correct_answer, distractors):
    """Validate and filter distractors for quality.

    Removes distractors that are:
    - Too similar to the correct answer (>85% overlap)
    - Duplicates of each other (>90% overlap)
    - Empty or too short

    Args:
        correct_answer: The correct option string.
        distractors: List of distractor strings.

    Returns:
        list[str] — filtered distractors.
    """
    from difflib import SequenceMatcher

    correct_lower = correct_answer.lower().strip()
    valid = []
    seen_lower = set()

    for d in distractors:
        d_stripped = d.strip()
        d_lower = d_stripped.lower()

        # Skip empty or very short
        if len(d_stripped) < 2:
            continue

        # Skip if too similar to correct answer
        if SequenceMatcher(None, correct_lower, d_lower).ratio() > 0.85:
            log.info(f"Distractor too similar to correct: '{d_stripped}'")
            continue

        # Skip if duplicate of an already-accepted distractor
        is_dup = False
        for seen in seen_lower:
            if SequenceMatcher(None, seen, d_lower).ratio() > 0.90:
                is_dup = True
                break
        if is_dup:
            continue

        valid.append(d_stripped)
        seen_lower.add(d_lower)

    return valid


def _build_question_text(path, hidden_component, lang):
    """Build a question by hiding one CSPOJ component.

    Args:
        path: CSPOJ path dict.
        hidden_component: Component to hide.
        lang: Language code.

    Returns:
        str — question text.
    """
    templates_es = {
        "object": "En {context}: {subject} {predicate} ¿qué?",
        "subject": "En {context}: ¿Qué/quién {predicate} {object}?",
        "predicate": "En {context}: ¿Qué relación existe entre {subject} y {object}?",
        "justification": "En {context}: {subject} {predicate} {object}. ¿Por qué?",
        "context": "{subject} {predicate} {object}. ¿En qué contexto?",
    }
    templates_en = {
        "object": "In {context}: {subject} {predicate} what?",
        "subject": "In {context}: What/who {predicate} {object}?",
        "predicate": "In {context}: What is the relationship between {subject} and {object}?",
        "justification": "In {context}: {subject} {predicate} {object}. Why?",
        "context": "{subject} {predicate} {object}. In what context?",
    }

    templates = templates_es if lang == "es" else templates_en
    template = templates.get(hidden_component, templates["object"])

    return template.format(
        context=path.get("context", ""),
        subject=path.get("subject", ""),
        predicate=path.get("predicate", ""),
        object=path.get("object", ""),
    )


def formulate_question_natural(path, component, template_question, lang="es",
                               model=None, temperature=None):
    """Reformulate a template question into natural language using LLM.

    Takes a mechanically-generated template question and makes it sound
    like a real university exam question.

    Args:
        path: CSPOJ path dict.
        component: Which CSPOJ component is being asked about.
        template_question: The template-generated question text.
        lang: Language code.
        model: Override model.
        temperature: Override temperature.

    Returns:
        str — natural language question text, or template_question as fallback.
    """
    lang_instruction = ai.get_language_instruction(lang)

    prompt = prompts.FORMULATE_QUESTION_PROMPT.format(
        template_question=template_question,
        context=path.get("context", ""),
        subject=path.get("subject", ""),
        predicate=path.get("predicate", ""),
        object=path.get("object", ""),
        component=component,
        correct_answer=path.get(component, ""),
        language_instruction=lang_instruction,
    )

    try:
        result = ai.call_llm_json(
            prompt, model=model, temperature=temperature,
            task="question_gen_mc",
        )
    except Exception as e:
        log.warning(f"NL formulation failed for path {path['id']}: {e}")
        return template_question

    if isinstance(result, dict):
        stem = result.get("stem", "")
        question = result.get("question", template_question)
        if stem:
            return f"{stem}\n{question}"
        return question

    return template_question


# ============================================================
# FREE TEXT GENERATION
# ============================================================

def generate_free_text(path, component, lang="es"):
    """Generate a Free Text question from a CSPOJ path.

    No LLM call needed — the question is built from the template
    and the correct answer is the hidden component.

    Args:
        path: CSPOJ path dict.
        component: Which component to hide.
        lang: Language code.

    Returns:
        dict — question with: id, type, path_id, component, question_text,
               correct_answer, explanation, difficulty, bloom_level
    """
    correct_answer = path.get(component, "")
    if not correct_answer:
        return None

    question_text = _build_question_text(path, component, lang)
    difficulty = defaults.CSPOJ_COMPONENT_DIFFICULTY.get(component, 1)

    # Bloom level depends on component difficulty
    bloom_level = min(difficulty, 6)

    return {
        "id": generate_id("q"),
        "type": Q_FREE_TEXT,
        "path_id": path["id"],
        "component": component,
        "question_text": question_text,
        "correct_answer": correct_answer,
        "explanation": path.get("justification", ""),
        "difficulty": difficulty,
        "bloom_level": bloom_level,
    }


# ============================================================
# ORCHESTRATOR
# ============================================================

def generate_questions(project_name, source_id=None, model=None,
                       question_types=None, components=None, natural=False,
                       progress_callback=None):
    """Generate questions from all CSPOJ paths in a project.

    For each path, generates questions of the specified types
    for the specified components.

    Args:
        project_name: Project name.
        source_id: Source ID (None for latest).
        model: Override LLM model.
        question_types: List of types to generate. Default: all three.
        components: List of components to hide. Default: all five.
        natural: If True, use LLM to reformulate questions in natural language.

    Returns:
        dict — preguntas.json structure with all generated questions.
    """
    # Defaults
    if question_types is None:
        question_types = [Q_TRUE_FALSE, Q_MULTIPLE_CHOICE, Q_FREE_TEXT]
    if components is None:
        components = HIDEABLE_COMPONENTS

    # Find source
    if source_id is None:
        sources = storage.list_sources(project_name)
        if not sources:
            raise FileNotFoundError(f"No sources in project '{project_name}'")
        source_id = sources[-1]

    # Load data.json
    data_path = storage.get_source_path(project_name, source_id, "data.json")
    data = storage.load_json(data_path)
    if not data:
        raise FileNotFoundError(
            f"No data.json for {source_id}. Run 'atenea extract' first."
        )

    paths = data.get("paths", [])
    if not paths:
        console.print("[yellow]No paths to generate questions from[/yellow]")
        return {"questions": [], "stats": {}}

    # Detect language
    sample = " ".join(p.get("context", "") for p in paths[:5])
    lang = ai.detect_language(sample)
    console.print(f"  Language detected: [bold]{lang}[/bold]")
    console.print(f"  Paths: {len(paths)}, Types: {question_types}, Components: {components}")
    if natural:
        console.print("  [bold]Natural language mode:[/bold] questions will be reformulated by LLM")

    all_questions = []

    with Progress(console=console, transient=True) as progress:
        total = len(paths) * len(components)
        task = progress.add_task("Generating questions...", total=total)
        done_count = 0

        for path in paths:
            for component in components:
                # Free text: no LLM call needed
                if Q_FREE_TEXT in question_types:
                    q = generate_free_text(path, component, lang=lang)
                    if q:
                        # NL reformulation for free text too if natural mode
                        if natural:
                            q["question_text"] = formulate_question_natural(
                                path, component, q["question_text"],
                                lang=lang, model=model,
                            )
                        q["source_text"] = path.get("justification", "")
                        all_questions.append(q)

                # True/False: needs LLM
                if Q_TRUE_FALSE in question_types:
                    result = generate_true_false(
                        path, component, model=model, lang=lang,
                    )
                    if result:
                        for q in result:
                            q["source_text"] = path.get("justification", "")
                        all_questions.extend(result)

                # Multiple Choice: needs LLM
                if Q_MULTIPLE_CHOICE in question_types:
                    q = generate_multiple_choice(
                        path, component, model=model, lang=lang,
                    )
                    if q:
                        # NL reformulation for MC questions
                        if natural:
                            q["question_text"] = formulate_question_natural(
                                path, component, q["question_text"],
                                lang=lang, model=model,
                            )
                        q["source_text"] = path.get("justification", "")
                        q["quality_score"] = _compute_question_quality(q, path)
                        all_questions.append(q)

                done_count += 1
                if progress_callback:
                    progress_callback(done_count, total, f"{len(all_questions)} questions")
                progress.advance(task)

    # Build output
    stats = _question_stats(all_questions)
    output = {
        "source_id": source_id,
        "created": storage.now_iso(),
        "language": lang,
        "natural_language": natural,
        "questions": all_questions,
        "stats": stats,
    }

    # Save
    output_path = storage.get_source_path(project_name, source_id, "preguntas.json")
    storage.save_json(output, output_path)

    # Also save at project level
    project_path = storage.get_project_path(project_name, "preguntas.json")
    storage.save_json(output, project_path)

    console.print(f"  Total questions generated: {len(all_questions)}")
    _display_question_stats(stats)

    return output


def generate_questions_lite(project_name, source_id=None, model=None,
                            max_paths=10, components=None, progress_callback=None):
    """Generate questions using only free-text (no LLM calls).

    Fast mode: generates free-text questions for all paths without
    any API calls. Useful for testing or when you want instant results.

    Args:
        project_name: Project name.
        source_id: Source ID (None for latest).
        model: Unused (kept for API consistency).
        max_paths: Maximum paths to process.
        components: Components to hide. Default: all five.

    Returns:
        dict — preguntas.json structure.
    """
    if components is None:
        components = HIDEABLE_COMPONENTS

    if source_id is None:
        sources = storage.list_sources(project_name)
        if not sources:
            raise FileNotFoundError(f"No sources in project '{project_name}'")
        source_id = sources[-1]

    data_path = storage.get_source_path(project_name, source_id, "data.json")
    data = storage.load_json(data_path)
    if not data:
        raise FileNotFoundError(f"No data.json for {source_id}")

    paths = data.get("paths", [])[:max_paths]
    sample = " ".join(p.get("context", "") for p in paths[:5])
    lang = ai.detect_language(sample)

    all_questions = []
    total = len(paths) * len(components)
    done = 0
    for path in paths:
        for component in components:
            q = generate_free_text(path, component, lang=lang)
            if q:
                all_questions.append(q)
            done += 1
            if progress_callback:
                progress_callback(done, total, f"{len(all_questions)} questions")

    stats = _question_stats(all_questions)
    output = {
        "source_id": source_id,
        "created": storage.now_iso(),
        "language": lang,
        "questions": all_questions,
        "stats": stats,
    }

    output_path = storage.get_source_path(project_name, source_id, "preguntas.json")
    storage.save_json(output, output_path)
    project_path = storage.get_project_path(project_name, "preguntas.json")
    storage.save_json(output, project_path)

    console.print(f"  Generated {len(all_questions)} free-text questions (no LLM)")
    return output


# ============================================================
# HELPERS
# ============================================================

def _compute_question_quality(question, path):
    """Compute a quality score [0, 1] for a generated question.

    Factors:
    - Path quality: number of point_ids (more = richer context)
    - Option count: 4 options (1 correct + 3 distractors) is ideal
    - Has justification: the path has a source text to trace back to

    Args:
        question: Question dict.
        path: Source CSPOJ path dict.

    Returns:
        float — quality score [0, 1].
    """
    score = 0.0

    # Path richness (0-0.4): paths with 5-9 point_ids are ideal
    n_pts = len(path.get("point_ids", []))
    if n_pts >= 5:
        score += 0.4
    elif n_pts >= 3:
        score += 0.2

    # Option count (0-0.3): 4 options is standard
    n_opts = question.get("n_options", len(question.get("options", [])))
    if n_opts >= 4:
        score += 0.3
    elif n_opts >= 3:
        score += 0.15

    # Justification present (0-0.2)
    if path.get("justification", "").strip():
        score += 0.2

    # Has source_text traceability (0-0.1)
    if question.get("source_text", "").strip():
        score += 0.1

    return round(score, 2)


def _question_stats(questions):
    """Compute statistics about generated questions."""
    by_type = {}
    by_component = {}
    by_difficulty = {}

    for q in questions:
        qtype = q.get("type", "unknown")
        by_type[qtype] = by_type.get(qtype, 0) + 1

        comp = q.get("component", "unknown")
        by_component[comp] = by_component.get(comp, 0) + 1

        diff = q.get("difficulty", 0)
        by_difficulty[diff] = by_difficulty.get(diff, 0) + 1

    return {
        "total": len(questions),
        "by_type": by_type,
        "by_component": by_component,
        "by_difficulty": by_difficulty,
    }


def _display_question_stats(stats):
    """Display question generation stats."""
    from rich.table import Table

    table = Table(title="Question Distribution")
    table.add_column("Category", style="bold")
    table.add_column("Count", justify="right")

    for qtype, count in stats.get("by_type", {}).items():
        table.add_row(f"Type: {qtype}", str(count))

    for comp, count in stats.get("by_component", {}).items():
        diff = defaults.CSPOJ_COMPONENT_DIFFICULTY.get(comp, "?")
        table.add_row(f"Component: {comp} (diff={diff})", str(count))

    console.print(table)
