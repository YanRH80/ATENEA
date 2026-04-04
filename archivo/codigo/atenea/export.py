"""
atenea/export.py — Modular Output Transforms

Transforms the internal data structure (knowledge.json, questions.json)
into external formats:
- .md  → Obsidian (master notes with links and tags)
- .csv → Anki (question flashcards)

These are outputs, NOT the app. The data structure is the product.
Each transform reads knowledge.json and produces a file.
"""

import csv
import io
import logging

from atenea import storage

log = logging.getLogger(__name__)


# ============================================================
# MARKDOWN EXPORT → Obsidian
# ============================================================

def export_md(project, output_path=None):
    """Export knowledge graph as Obsidian-compatible markdown.

    Creates a master notes file with:
    - Keywords as headers with definitions, tags, and page refs
    - Associations as linked relationships
    - Sequences as visual chains
    - Sets as grouped lists

    Args:
        project: Project name
        output_path: Output file path (default: project dir)

    Returns:
        str: Path to generated file
    """
    knowledge_path = str(storage.get_project_path(project, "knowledge.json"))
    knowledge = storage.load_json(knowledge_path)
    if not knowledge:
        raise ValueError(f"No knowledge found for '{project}'")

    lines = []
    lines.append(f"# {project.title()} — Apuntes Maestros")
    lines.append("")
    lines.append(f"*Generado por Atenea*")
    lines.append(f"*Fuentes: {', '.join(knowledge.get('sources', []))}*")
    lines.append("")

    # Keywords
    keywords = knowledge.get("keywords", [])
    if keywords:
        lines.append("## Keywords")
        lines.append("")
        for kw in keywords:
            term = kw.get("term", "")
            definition = kw.get("definition", "")
            tags = kw.get("tags", [])
            page = kw.get("page", "")
            source = kw.get("source", "")

            # Obsidian tags
            tag_str = " ".join(f"#{t.replace(' ', '-')}" for t in tags) if tags else ""

            lines.append(f"### [[{term}]]")
            lines.append(f"{definition}")
            if tag_str:
                lines.append(f"Tags: {tag_str}")
            if page and source:
                lines.append(f"*Fuente: {source}, p.{page}*")
            lines.append("")

    # Associations
    associations = knowledge.get("associations", [])
    if associations:
        lines.append("## Asociaciones")
        lines.append("")
        for assoc in associations:
            from_t = assoc.get("from_term", "")
            to_t = assoc.get("to_term", "")
            relation = assoc.get("relation", "")
            desc = assoc.get("description", "")
            justification = assoc.get("justification", "")
            page = assoc.get("page", "")

            lines.append(f"- **[[{from_t}]]** —*{relation}*→ **[[{to_t}]]**")
            if desc:
                lines.append(f"  {desc}")
            if justification:
                lines.append(f"  > {justification}")
            lines.append("")

    # Sequences
    sequences = knowledge.get("sequences", [])
    if sequences:
        lines.append("## Secuencias")
        lines.append("")
        for seq in sequences:
            nodes = seq.get("nodes", [])
            desc = seq.get("description", "")
            pages = seq.get("pages", [])

            chain = " → ".join(f"[[{n}]]" for n in nodes)
            lines.append(f"### {desc}")
            lines.append(f"{chain}")
            if pages:
                lines.append(f"*Páginas: {', '.join(str(p) for p in pages)}*")
            lines.append("")

    # Sets
    sets = knowledge.get("sets", [])
    if sets:
        lines.append("## Conjuntos")
        lines.append("")
        for s in sets:
            name = s.get("name", "")
            terms = s.get("keyword_terms", [])
            desc = s.get("description", "")

            lines.append(f"### {name}")
            if desc:
                lines.append(f"{desc}")
            for t in terms:
                lines.append(f"- [[{t}]]")
            lines.append("")

    content = "\n".join(lines)

    # Write file
    if output_path is None:
        output_path = str(storage.get_project_path(project, f"{project}-apuntes.md"))
    storage.save_text(content, output_path)

    log.info(f"Exported {len(keywords)} keywords, {len(associations)} associations, "
             f"{len(sequences)} sequences to {output_path}")
    return output_path


# ============================================================
# CSV EXPORT → Anki
# ============================================================

def export_csv(project, output_path=None):
    """Export questions as Anki-compatible CSV.

    Format: Front (question + options), Back (answer + justification)
    Anki import settings: Separator=tab, allow HTML=true

    Args:
        project: Project name
        output_path: Output file path (default: project dir)

    Returns:
        str: Path to generated file
    """
    questions_path = str(storage.get_project_path(project, "questions.json"))
    q_data = storage.load_json(questions_path)
    if not q_data or not q_data.get("questions"):
        raise ValueError(f"No questions for '{project}'")

    questions = q_data["questions"]

    if output_path is None:
        output_path = str(storage.get_project_path(project, f"{project}-anki.csv"))

    output = io.StringIO()
    writer = csv.writer(output, delimiter="\t")

    for q in questions:
        # Front: context + question + options
        front_parts = []
        if q.get("context"):
            front_parts.append(q["context"])
        front_parts.append(f"\n{q['question']}")

        options = q.get("options", {})
        for key in ["A", "B", "C", "D"]:
            if key in options:
                front_parts.append(f"{key}) {options[key]}")

        front = "\n".join(front_parts)

        # Back: correct answer + justification
        correct = q.get("correct", "")
        back_parts = [f"Respuesta: {correct}) {options.get(correct, '')}"]
        if q.get("justification"):
            back_parts.append(f"\n{q['justification']}")

        back = "\n".join(back_parts)

        # Tags
        tags = " ".join(q.get("targets", []))

        writer.writerow([front, back, tags])

    content = output.getvalue()
    storage.save_text(content, output_path)

    log.info(f"Exported {len(questions)} questions to {output_path}")
    return output_path
