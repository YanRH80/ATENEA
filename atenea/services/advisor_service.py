"""
atenea/services/advisor_service.py — Collection advisor logic (UI-agnostic)

Pure functions for:
- Document summarization via LLM
- Collection analysis (clusters, roadmap, insights)
- Advisor pipeline orchestration

No display imports. Returns data structures for any frontend to render.
"""

import logging

from atenea import storage
from atenea.ai import call_llm, call_llm_json, detect_language, get_language_instruction
from atenea.ingest import extract_text
from config.prompts import SUMMARIZE_DOCUMENT_PROMPT, COLLECTION_ADVISOR_PROMPT

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 4000


def summarize_document(text, metadata, lang="es"):
    """Generate a 2-3 sentence AI summary of a single document.

    Args:
        text: Extracted text from the PDF (will be truncated).
        metadata: Bibliography entry dict.
        lang: Language code.

    Returns:
        str: AI-generated summary.
    """
    prompt = SUMMARIZE_DOCUMENT_PROMPT.format(
        title=metadata.get("title", "Sin titulo"),
        evidence_level=metadata.get("evidence_level", "4"),
        document_type=metadata.get("type", "document"),
        text=text[:MAX_TEXT_CHARS],
        language_instruction=get_language_instruction(lang),
    )
    return call_llm(prompt, task="summary")


def summarize_collection_documents(project, bibliography, on_progress=None):
    """Generate AI summaries for all documents missing one.

    Args:
        project: Project name.
        bibliography: List of bibliography entry dicts.
        on_progress: Optional callback(current, total, message).

    Returns:
        list[dict]: Updated bibliography with 'ai_summary' populated.
    """
    pending = [e for e in bibliography if not e.get("ai_summary") and not e.get("removed")]
    total = len(pending)

    if total == 0:
        return bibliography

    sample_lang = "es"

    for i, entry in enumerate(pending):
        source_id = entry.get("source_id")
        title = entry.get("title", "?")

        if on_progress:
            on_progress(i + 1, total, f"Resumiendo: {title[:40]}...")

        if not source_id:
            log.warning(f"Entry sin source_id: {title}")
            continue

        text = load_source_text(project, source_id)
        if not text:
            log.warning(f"Sin texto extraible para {source_id} ({title})")
            entry["ai_summary"] = "(texto no disponible)"
            continue

        if i == 0:
            sample_lang = detect_language(text[:1000])

        try:
            summary = summarize_document(text, entry, lang=sample_lang)
            entry["ai_summary"] = summary
        except Exception as e:
            log.error(f"Error resumiendo {source_id}: {e}")
            entry["ai_summary"] = f"(error: {e})"

    return bibliography


def analyze_collection(bibliography, lang="es"):
    """Analyze a collection and produce a structured study plan.

    Args:
        bibliography: List of bibliography entries (with ai_summary populated).
        lang: Language code.

    Returns:
        dict: Structured analysis with keys:
            collection_profile, topic_clusters, study_roadmap,
            estimated_scope, key_insights
    """
    active = [e for e in bibliography if not e.get("removed")]
    if not active:
        return empty_report()

    lines = []
    for e in active:
        summary = e.get("ai_summary", e.get("abstract", "")[:100])
        lines.append(
            f"- [{e.get('id', '?')}] \"{e.get('title', '?')}\" "
            f"(tipo: {e.get('type', '?')}, evidencia: {e.get('evidence_level', '?')}, "
            f"grado: {e.get('recommendation_grade', '?')})\n"
            f"  Resumen: {summary}"
        )
    collection_summary = "\n".join(lines)

    prompt = COLLECTION_ADVISOR_PROMPT.format(
        collection_summary=collection_summary,
        language_instruction=get_language_instruction(lang),
    )

    return call_llm_json(prompt, task="advisor")


def run_advisor_pipeline(project, skip_summaries=False, on_progress=None):
    """Orchestrate full advisor workflow without any UI dependencies.

    Args:
        project: Project name.
        skip_summaries: If True, skip AI summary generation.
        on_progress: Optional callback(step, message).

    Returns:
        dict: The advisor report.
    """
    bibliography = storage.load_bibliography(project)

    if not bibliography:
        return empty_report()

    # Step 1: Generate summaries
    if not skip_summaries:
        pending_count = sum(1 for e in bibliography if not e.get("ai_summary") and not e.get("removed"))
        if pending_count > 0:
            if on_progress:
                on_progress("summaries_start", f"Generando resumenes para {pending_count} documentos...")

            bibliography = summarize_collection_documents(project, bibliography, on_progress)
            storage.save_bibliography(project, bibliography)

            if on_progress:
                on_progress("summaries_done", "Resumenes generados.")

    # Step 2: Analyze collection
    if on_progress:
        on_progress("analysis_start", "Analizando coleccion...")

    lang = detect_language(
        " ".join(e.get("ai_summary", "") for e in bibliography if e.get("ai_summary"))[:2000]
        or "es"
    )
    report = analyze_collection(bibliography, lang=lang)

    # Save advisor report
    advisor_path = storage.get_project_path(project, "advisor.json")
    storage.save_json(report, str(advisor_path))

    if on_progress:
        on_progress("done", "Analisis completado.")

    return report


def load_source_text(project, source_id):
    """Load extracted text for a source, extracting from PDF if needed.

    Returns:
        str: Concatenated text from all pages, or "" if unavailable.
    """
    text_path = storage.get_source_path(project, source_id, "text.json")
    text_data = storage.load_json(str(text_path))

    if text_data and text_data.get("pages"):
        return "\n\n".join(p["text"] for p in text_data["pages"] if p.get("text"))

    pdf_path = storage.get_source_path(project, source_id, "original.pdf")
    if pdf_path.exists():
        log.info(f"Extrayendo texto de {source_id}/original.pdf")
        try:
            pages = extract_text(str(pdf_path))
            storage.save_json({"pages": pages}, str(text_path))
            return "\n\n".join(p["text"] for p in pages if p.get("text"))
        except Exception as e:
            log.error(f"Error extrayendo texto de {source_id}: {e}")
            return ""

    return ""


def empty_report():
    """Return an empty advisor report structure."""
    return {
        "collection_profile": "",
        "topic_clusters": [],
        "study_roadmap": [],
        "estimated_scope": {
            "total_documents": 0,
            "estimated_hours": 0.0,
            "complexity": "N/A",
        },
        "key_insights": [],
    }
