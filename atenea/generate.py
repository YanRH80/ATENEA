"""
atenea/generate.py — MIR Question Generation via RAG + LLM

Pipeline:
1. Select targets from knowledge.json (prioritize unknown > testing)
2. Retrieve source text for target pages (RAG without embeddings)
3. Send knowledge context + source text + question pattern to LLM
4. Parse and save questions to questions.json

The knowledge graph IS the retrieval index: each keyword/association
has source + page → look up text.json → include in LLM prompt.
"""

import logging
import random

from atenea import ai, storage
from atenea.utils import generate_id
from config import prompts, defaults

log = logging.getLogger(__name__)


# ============================================================
# QUESTION PATTERNS — High-yield MIR archetypes
# ============================================================

PATTERNS = [
    {
        "name": "caso_clinico_diagnostico",
        "description": (
            "Viñeta clínica con variables (edad, sexo, síntomas, labs) "
            "→ ¿Cuál es el diagnóstico más probable? "
            "Distractores: diagnósticos del mismo sistema/presentación similar."
        ),
    },
    {
        "name": "variable_interpretacion",
        "description": (
            "Se presenta un valor de laboratorio o hallazgo clínico "
            "→ ¿Qué indica / cuál es la interpretación correcta? "
            "Distractores: otras interpretaciones plausibles del mismo valor."
        ),
    },
    {
        "name": "farmaco_contraindicacion",
        "description": (
            "Paciente con patología X toma fármaco Y "
            "→ ¿Cuál es la contraindicación / efecto adverso más relevante? "
            "Distractores: efectos de fármacos similares."
        ),
    },
    {
        "name": "secuencia_fisiopatologica",
        "description": (
            "Se describe un mecanismo incompleto "
            "→ ¿Cuál es el siguiente paso en la cascada? "
            "Distractores: pasos de cascadas relacionadas pero diferentes."
        ),
    },
    {
        "name": "clasificacion_criterios",
        "description": (
            "Se pregunta por criterios diagnósticos, estadificación o clasificación "
            "→ ¿Cuál de los siguientes es un criterio de X? "
            "Distractores: criterios de clasificaciones similares."
        ),
    },
    {
        "name": "tratamiento_eleccion",
        "description": (
            "Paciente con diagnóstico establecido "
            "→ ¿Cuál es el tratamiento de elección / primera línea? "
            "Distractores: tratamientos de segunda línea o de patologías similares."
        ),
    },
    {
        "name": "diferencial_excluyente",
        "description": (
            "Se presentan varias opciones diagnósticas "
            "→ ¿Cuál de las siguientes NO es causa de X? "
            "Requiere conocer todo el set para excluir."
        ),
    },
    {
        "name": "asociacion_causal",
        "description": (
            "Se pregunta por relaciones causa-efecto entre conceptos "
            "→ ¿Qué causa / inhibe / produce X? "
            "Distractores: causas de condiciones relacionadas."
        ),
    },
]


# ============================================================
# TARGET SELECTION — Prioritize unknown > testing > known
# ============================================================

def select_targets(knowledge, n=10):
    """Select knowledge items to test, prioritizing unknown status.

    Returns a mix of keywords, associations, and sequences.
    Priority: unknown > testing > known (never tested items first).

    Returns:
        list[dict]: Selected items with type annotation.
    """
    all_items = []

    for kw in knowledge.get("keywords", []):
        all_items.append({"type": "keyword", "item": kw})

    for assoc in knowledge.get("associations", []):
        all_items.append({"type": "association", "item": assoc})

    for seq in knowledge.get("sequences", []):
        all_items.append({"type": "sequence", "item": seq})

    # Sort by status priority
    status_priority = {"unknown": 0, "testing": 1, "known": 2}
    all_items.sort(key=lambda x: status_priority.get(x["item"].get("status", "unknown"), 0))

    # Take top n, with some randomness within same priority
    selected = []
    by_status = {}
    for item in all_items:
        status = item["item"].get("status", "unknown")
        by_status.setdefault(status, []).append(item)

    for status in ["unknown", "testing", "known"]:
        items = by_status.get(status, [])
        random.shuffle(items)
        for item in items:
            if len(selected) >= n:
                break
            selected.append(item)
        if len(selected) >= n:
            break

    return selected


# ============================================================
# RAG: Retrieve source text for targets
# ============================================================

def retrieve_context(targets, project):
    """Retrieve source text for a set of targets using page references.

    This is RAG without embeddings: the knowledge graph metadata
    (source + page) IS the retrieval index.

    Returns:
        tuple: (knowledge_context: str, source_text: str)
    """
    # Collect unique source+page pairs
    pages_needed = {}  # source_id → set of page numbers
    for t in targets:
        item = t["item"]
        source = item.get("source", "")
        if not source:
            continue

        # Keywords and associations have single page
        page = item.get("page")
        if page:
            pages_needed.setdefault(source, set()).add(page)

        # Sequences have multiple pages
        for p in item.get("pages", []):
            pages_needed.setdefault(source, set()).add(p)

    # Load text for those pages
    source_text_parts = []
    for source_id, page_nums in pages_needed.items():
        try:
            text_path = storage.get_source_path(project, source_id, "text.json")
            data = storage.load_json(str(text_path))
            if not data or "pages" not in data:
                continue
            for page in data["pages"]:
                if page["page"] in page_nums:
                    source_text_parts.append(
                        f"--- Página {page['page']} ({source_id}) ---\n{page['text']}"
                    )
        except Exception as e:
            log.warning(f"Could not load text for {source_id}: {e}")

    source_text = "\n\n".join(source_text_parts)

    # Build knowledge context summary
    knowledge_lines = []
    for t in targets:
        item = t["item"]
        if t["type"] == "keyword":
            knowledge_lines.append(f"- KEYWORD: {item['term']} — {item.get('definition', '')}")
        elif t["type"] == "association":
            knowledge_lines.append(
                f"- ASSOCIATION: {item.get('from_term', '')} "
                f"--[{item.get('relation', '')}]--> {item.get('to_term', '')} "
                f"| {item.get('description', '')}"
            )
        elif t["type"] == "sequence":
            nodes = " → ".join(item.get("nodes", []))
            knowledge_lines.append(
                f"- SEQUENCE: {nodes} | {item.get('description', '')}"
            )
    knowledge_context = "\n".join(knowledge_lines)

    return knowledge_context, source_text


# ============================================================
# GENERATE QUESTIONS via LLM
# ============================================================

def generate_questions(knowledge_context, source_text, citekey, n=5, pattern=None, model=None):
    """Send knowledge + source text to LLM to generate MIR questions.

    Args:
        knowledge_context: Formatted knowledge items string
        source_text: Retrieved source pages text
        citekey: Citation key for references
        n: Number of questions to generate
        pattern: Specific pattern dict, or None for random
        model: LLM model override

    Returns:
        list[dict]: Generated questions
    """
    if pattern is None:
        pattern = random.choice(PATTERNS)

    # Detect language from source text
    lang = ai.detect_language(source_text[:500]) if source_text else "es"

    prompt = prompts.GENERATE_QUESTION_PROMPT.format(
        n_questions=n,
        pattern_name=pattern["name"],
        pattern_description=pattern["description"],
        knowledge_context=knowledge_context,
        source_text=source_text[:15000],  # Cap source text to avoid timeout
        citekey=citekey,
        language_instruction=ai.get_language_instruction(lang),
    )

    result = ai.call_llm_json(prompt, model=model, task="question_gen")

    # Normalize: accept both list and dict with "questions" key
    if isinstance(result, dict):
        result = result.get("questions", [])

    # Assign IDs and metadata
    questions = []
    for q in result:
        q["id"] = generate_id("q")
        q["pattern"] = pattern["name"]
        questions.append(q)

    return questions


# ============================================================
# ORCHESTRATOR
# ============================================================

def run_generate(project, n=25, model=None):
    """Generate MIR questions from knowledge graph + source text.

    Pipeline:
    1. Load knowledge.json
    2. Select targets (prioritize unknown)
    3. Retrieve source text (RAG via page references)
    4. Generate questions in batches using different patterns
    5. Save to questions.json

    Args:
        project: Project name
        n: Total number of questions to generate
        model: LLM model override

    Returns:
        dict: Updated questions data
    """
    # Load knowledge
    knowledge_path = str(storage.get_project_path(project, "knowledge.json"))
    knowledge = storage.load_json(knowledge_path)
    if not knowledge or not knowledge.get("keywords"):
        raise ValueError(f"No knowledge found for '{project}'. Run 'atenea study' first.")

    # Get citekey from first source
    sources = knowledge.get("sources", [])
    citekey = project  # fallback
    if sources:
        meta_path = storage.get_source_path(project, sources[0], "source-meta.json")
        meta = storage.load_json(str(meta_path))
        citekey = meta.get("citekey", project) if meta else project

    # Select targets
    targets = select_targets(knowledge, n=min(n * 2, len(knowledge.get("keywords", [])) + len(knowledge.get("associations", []))))

    # Retrieve source text (RAG)
    knowledge_context, source_text = retrieve_context(targets, project)
    log.info(f"Retrieved {len(source_text):,} chars of source text for {len(targets)} targets")

    # Generate in batches of ~5 questions with different patterns
    all_questions = []
    batch_size = 5
    remaining = n

    patterns_cycle = PATTERNS.copy()
    random.shuffle(patterns_cycle)
    pattern_idx = 0

    while remaining > 0:
        batch_n = min(batch_size, remaining)
        pattern = patterns_cycle[pattern_idx % len(patterns_cycle)]
        pattern_idx += 1

        log.info(f"Generating {batch_n} questions (pattern: {pattern['name']})")
        try:
            batch_questions = generate_questions(
                knowledge_context, source_text, citekey,
                n=batch_n, pattern=pattern, model=model
            )
            all_questions.extend(batch_questions)
            remaining -= len(batch_questions)
        except Exception as e:
            log.error(f"Failed to generate batch: {e}")
            remaining -= batch_n  # Skip this batch, continue

    log.info(f"Generated {len(all_questions)} questions total")

    # Load existing questions and append
    questions_path = str(storage.get_project_path(project, "questions.json"))
    existing = storage.load_json(questions_path) or {"questions": []}
    existing.setdefault("questions", [])
    existing["questions"].extend(all_questions)
    existing["updated"] = storage.now_iso()

    # Save
    storage.save_json(existing, questions_path)

    return existing
