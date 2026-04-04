"""
atenea/study.py — Knowledge Extraction via LLM

Reads source text and condenses it into structured knowledge:
- Keywords: key concepts with definitions
- Associations: relationships between keywords (A → B)
- Sequences: chains of 5-9 connected nodes (7±2 Miller rule)
- Sets: semantic groupings of keywords
- Maps: higher-order structures grouping sequences

Pipeline: text.json → LLM → knowledge.json
"""

import logging

from atenea import ai, storage
from atenea.utils import generate_id
from config import prompts, defaults

log = logging.getLogger(__name__)


# ============================================================
# LOAD SOURCE TEXT
# ============================================================

def load_source_text(project, source_id):
    """Load extracted text for a source, concatenated by page.

    Returns:
        tuple: (full_text: str, pages: list[dict] with page/text)
    """
    text_path = storage.get_source_path(project, source_id, "text.json")
    data = storage.load_json(str(text_path))
    if not data or "pages" not in data:
        raise ValueError(f"No text.json found for {project}/{source_id}")

    pages = data["pages"]  # [{"page": 1, "text": "..."}, ...]
    full_text = ""
    for page in pages:
        full_text += f"\n\n--- Página {page['page']} ---\n{page['text']}"

    return full_text.strip(), pages


# ============================================================
# CONDENSE TO KNOWLEDGE
# ============================================================

def condense_to_knowledge(text, source_id, citekey, model=None):
    """Send text to LLM and extract structured knowledge.

    Returns:
        dict with: keywords, associations, sequences
    """
    prompt = prompts.CONDENSE_PROMPT.format(
        text=text,
        citekey=citekey,
        min_elements=defaults.MIN_ELEMENTS,
        max_elements=defaults.MAX_ELEMENTS,
        language_instruction=ai.get_language_instruction(
            ai.detect_language(text[:500])
        ),
    )

    result = ai.call_llm_json(prompt, model=model, task="extraction")

    # Validate and assign IDs
    keywords = []
    for kw in result.get("keywords", []):
        kw["id"] = generate_id("kw")
        kw["source"] = source_id
        kw["status"] = "unknown"
        keywords.append(kw)

    associations = []
    for assoc in result.get("associations", []):
        assoc["id"] = generate_id("as")
        assoc["source"] = source_id
        assoc["status"] = "unknown"
        associations.append(assoc)

    sequences = []
    for seq in result.get("sequences", []):
        seq["id"] = generate_id("sq")
        seq["source"] = source_id
        seq["status"] = "unknown"
        # Validate 7±2 rule
        nodes = seq.get("nodes", [])
        if len(nodes) < defaults.MIN_ELEMENTS:
            log.warning(f"Sequence {seq['id']} has {len(nodes)} nodes (min {defaults.MIN_ELEMENTS})")
        sequences.append(seq)

    sets = []
    for s in result.get("sets", []):
        s["id"] = generate_id("st")
        s["source"] = source_id
        sets.append(s)

    return {
        "keywords": keywords,
        "associations": associations,
        "sequences": sequences,
        "sets": sets,
    }


# ============================================================
# MERGE KNOWLEDGE
# ============================================================

def merge_knowledge(existing, new_items):
    """Merge new knowledge into existing, avoiding duplicates.

    Simple merge: append new items. Duplicate detection by term match
    for keywords, by description match for associations/sequences.
    """
    # Ensure all keys exist
    for key in ["keywords", "associations", "sequences", "sets", "maps", "sources"]:
        existing.setdefault(key, [])

    # Build lookup sets for dedup
    existing_kw_terms = {kw["term"].lower() for kw in existing["keywords"]}
    existing_assoc_descs = {a["description"].lower() for a in existing.get("associations", [])}

    merged_kw = 0
    for kw in new_items.get("keywords", []):
        if kw["term"].lower() not in existing_kw_terms:
            existing["keywords"].append(kw)
            existing_kw_terms.add(kw["term"].lower())
            merged_kw += 1

    merged_assoc = 0
    for assoc in new_items.get("associations", []):
        if assoc["description"].lower() not in existing_assoc_descs:
            existing["associations"].append(assoc)
            existing_assoc_descs.add(assoc["description"].lower())
            merged_assoc += 1

    # Sequences and sets: always append (hard to dedup meaningfully)
    for seq in new_items.get("sequences", []):
        existing.setdefault("sequences", []).append(seq)
    for s in new_items.get("sets", []):
        existing.setdefault("sets", []).append(s)

    log.info(f"Merged: {merged_kw} keywords, {merged_assoc} associations, "
             f"{len(new_items.get('sequences', []))} sequences")

    existing["updated"] = storage.now_iso()
    return existing


# ============================================================
# ORCHESTRATOR
# ============================================================

PAGES_PER_BATCH = 5  # Process ~5 pages at a time to avoid LLM timeouts


def _batch_pages(pages, batch_size=PAGES_PER_BATCH):
    """Split pages into batches, returning text chunks with page ranges."""
    batches = []
    for i in range(0, len(pages), batch_size):
        batch = pages[i:i + batch_size]
        text = ""
        for page in batch:
            text += f"\n\n--- Página {page['page']} ---\n{page['text']}"
        batches.append(text.strip())
    return batches


def run_study(project, source_id=None, model=None):
    """Extract knowledge from a source and merge into knowledge.json.

    Processes text in batches of ~5 pages to avoid LLM timeouts.
    Each batch is sent independently, results are merged.

    Args:
        project: Project name
        source_id: Specific source (default: latest)
        model: LLM model override

    Returns:
        dict: Updated knowledge
    """
    # Resolve source
    if source_id is None:
        sources = storage.list_sources(project)
        if not sources:
            raise ValueError(f"No sources in project '{project}'")
        source_id = sources[-1]

    # Load source metadata for citekey
    meta_path = storage.get_source_path(project, source_id, "source-meta.json")
    meta = storage.load_json(str(meta_path)) or {}
    citekey = meta.get("citekey", source_id)

    # Load text
    full_text, pages = load_source_text(project, source_id)

    # Process in batches
    batches = _batch_pages(pages)
    log.info(f"Processing {len(pages)} pages in {len(batches)} batches")

    all_knowledge = {"keywords": [], "associations": [], "sequences": [], "sets": []}

    for i, batch_text in enumerate(batches, 1):
        log.info(f"Batch {i}/{len(batches)} ({len(batch_text):,} chars)")
        batch_result = condense_to_knowledge(batch_text, source_id, citekey, model=model)

        # Accumulate
        for key in all_knowledge:
            all_knowledge[key].extend(batch_result.get(key, []))

    log.info(f"Extracted: {len(all_knowledge['keywords'])} keywords, "
             f"{len(all_knowledge['associations'])} associations, "
             f"{len(all_knowledge['sequences'])} sequences, "
             f"{len(all_knowledge['sets'])} sets")

    # Load existing knowledge and merge
    knowledge_path = str(storage.get_project_path(project, "knowledge.json"))
    existing = storage.load_json(knowledge_path) or {}

    # Track sources
    existing.setdefault("sources", [])
    if source_id not in existing["sources"]:
        existing["sources"].append(source_id)

    merged = merge_knowledge(existing, all_knowledge)

    # Save
    storage.save_json(merged, knowledge_path)

    return merged
