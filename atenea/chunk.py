"""
atenea/chunk.py — Step 2: Markdown to Structured JSON (clean-md.json)

Parses raw markdown into a structured database of sections, lines, and
keywords. This is the "database phase" — no AI is used. The output is
deterministic and reproducible, and serves as the foundation for all
subsequent AI-powered steps.

Pipeline position:
    [raw_output.md] → chunk.py → clean-md.json → [extract.py]

== How this works ==

1. split_into_sections(): Detects markdown headers (# ## ### etc.) and
   builds a hierarchical tree of sections with parent/child relationships.

2. extract_lines(): Numbers every non-empty line and tags it with the
   section(s) it belongs to.

3. extract_keywords(): Tokenizes all text, removes stopwords (ES+EN),
   and returns unique significant terms sorted by frequency.

4. build_clean_md(): Assembles the final JSON structure.

== Why this matters for downstream modules ==

- extract.py sends one section at a time to the LLM (saves tokens)
- The keywords list serves as candidates for the LLM to filter (reduces hallucination)
- Line numbers allow verifying that CSPOJ justifications are verbatim
- The hierarchical section tree enables scoped knowledge extraction

== No AI in this step ==

This step is purely procedural (regex + tokenization). Benefits:
- Zero cost (no API calls)
- Deterministic output (same input → same output always)
- Fast iteration (change parameters, re-run instantly)
"""

import re
from collections import Counter

from rich.console import Console

from atenea import storage
from atenea.utils import generate_id

console = Console()

# ============================================================
# STOPWORDS — Common words to exclude from keywords
# Combined ES + EN. Extend as needed.
# ============================================================

STOPWORDS_EN = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "not", "no", "nor", "as", "if", "then",
    "than", "so", "such", "more", "most", "also", "into", "over", "after",
    "before", "between", "through", "about", "up", "out", "all", "each",
    "every", "both", "few", "some", "any", "other", "which", "who", "whom",
    "what", "when", "where", "how", "why", "there", "here", "very", "just",
    "only", "own", "same", "our", "we", "they", "he", "she", "you", "i",
    "me", "my", "your", "his", "her", "their", "them", "us", "one", "two",
})

STOPWORDS_ES = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "pero",
    "en", "de", "del", "al", "con", "por", "para", "sin", "sobre", "entre",
    "es", "son", "fue", "ser", "estar", "ha", "han", "hay", "como", "más",
    "menos", "muy", "ya", "se", "le", "lo", "que", "no", "ni", "si", "su",
    "sus", "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "aquel", "aquella", "aquellos", "aquellas", "yo", "tú", "él", "ella",
    "nosotros", "ellos", "ellas", "me", "te", "nos", "les", "mi", "tu",
    "qué", "cómo", "dónde", "cuándo", "por qué", "cada", "otro", "otra",
    "otros", "otras", "todo", "toda", "todos", "todas", "mismo", "misma",
    "puede", "pueden", "así", "también", "desde", "hasta", "cuando", "donde",
})

STOPWORDS = STOPWORDS_EN | STOPWORDS_ES

# Minimum word length to consider as a keyword
MIN_KEYWORD_LENGTH = 3

# Minimum frequency to include a keyword
MIN_KEYWORD_FREQUENCY = 1


# ============================================================
# CORE FUNCTIONS
# ============================================================

def load_markdown(project_name, source_id=None):
    """Load the raw markdown file for a project source.

    If source_id is None, uses the latest (highest numbered) source.

    Args:
        project_name: Name of the project.
        source_id: Source ID (e.g., "src-001"). None for latest.

    Returns:
        tuple (str, str) — (markdown_text, source_id used).

    Raises:
        FileNotFoundError: If no markdown file exists.
    """
    if source_id is None:
        sources = storage.list_sources(project_name)
        if not sources:
            raise FileNotFoundError(
                f"No sources found in project '{project_name}'. "
                f"Run 'atenea convert' first."
            )
        source_id = sources[-1]  # Latest source

    md_path = storage.get_source_path(project_name, source_id, "raw_output.md")
    text = storage.load_text(md_path)
    if not text:
        raise FileNotFoundError(
            f"No markdown file found at {md_path}. "
            f"Run 'atenea convert' first."
        )
    return text, source_id


def split_into_sections(md_text):
    """Split markdown text into hierarchical sections based on headers.

    Detects markdown headers (# Level 1, ## Level 2, etc.) and creates
    a flat list of section dicts with parent-child relationships.

    Algorithm:
    1. Scan each line for header patterns (^#{1,6} )
    2. For each header found, create a section with start_line
    3. Set end_line of the previous section to the line before this one
    4. Assign parent_id by finding the nearest ancestor with a lower level

    Args:
        md_text: Complete markdown text.

    Returns:
        list[dict] — sections, each with:
            id: Unique section ID (e.g., "sec_a1b2c3d4")
            title: Header text (without # markers)
            level: Heading level (1-6)
            parent_id: ID of parent section (None for top-level)
            start_line: First line number of section content
            end_line: Last line number of section content
    """
    lines = md_text.split("\n")
    header_pattern = re.compile(r"^(#{1,6})\s+(.+)$")
    sections = []
    # Stack to track parent sections: [(level, section_id), ...]
    parent_stack = []

    for line_num, line in enumerate(lines, start=1):
        match = header_pattern.match(line.strip())
        if not match:
            continue

        level = len(match.group(1))
        title = match.group(2).strip()
        section_id = generate_id("sec")

        # Find parent: pop stack until we find a section with lower level
        while parent_stack and parent_stack[-1][0] >= level:
            parent_stack.pop()
        parent_id = parent_stack[-1][1] if parent_stack else None

        # Close previous section's end_line
        if sections:
            sections[-1]["end_line"] = line_num - 1

        section = {
            "id": section_id,
            "title": title,
            "level": level,
            "parent_id": parent_id,
            "start_line": line_num + 1,  # Content starts after header
            "end_line": len(lines),      # Will be updated by next section
        }
        sections.append(section)
        parent_stack.append((level, section_id))

    # If no sections found, create a single root section
    if not sections:
        sections.append({
            "id": generate_id("sec"),
            "title": "Document",
            "level": 0,
            "parent_id": None,
            "start_line": 1,
            "end_line": len(lines),
        })

    return sections


def extract_lines(md_text, sections):
    """Extract all non-empty lines with their section assignments.

    Each line gets a number and is tagged with the section(s) it belongs to.
    A line can belong to multiple sections if it falls within nested sections.

    Args:
        md_text: Complete markdown text.
        sections: List of section dicts from split_into_sections().

    Returns:
        list[dict] — lines, each with:
            line_number: 1-based line number
            content: The text content of the line
            section_ids: List of section IDs this line belongs to
    """
    raw_lines = md_text.split("\n")
    result = []

    for line_num, content in enumerate(raw_lines, start=1):
        stripped = content.strip()
        # Skip empty lines and pure header lines
        if not stripped or re.match(r"^#{1,6}\s+", stripped):
            continue

        # Find which sections this line belongs to
        section_ids = []
        for section in sections:
            if section["start_line"] <= line_num <= section["end_line"]:
                section_ids.append(section["id"])

        result.append({
            "line_number": line_num,
            "content": stripped,
            "section_ids": section_ids,
        })

    return result


def extract_keywords(lines):
    """Extract unique significant keywords from all lines.

    Purely heuristic (no AI):
    1. Tokenize all line content into words
    2. Normalize to lowercase
    3. Filter out stopwords (ES + EN)
    4. Filter out short words (< MIN_KEYWORD_LENGTH)
    5. Extract bigrams and trigrams for compound terms
    6. Count frequencies
    7. Return unique terms sorted by frequency (descending)

    Args:
        lines: List of line dicts from extract_lines().

    Returns:
        list[str] — unique keywords sorted by frequency (most frequent first).
            Includes both single words and compound terms (bigrams/trigrams).
    """
    # Tokenize: split on non-alphanumeric characters (keeps accented chars)
    word_pattern = re.compile(r"[a-záéíóúñüàèìòùâêîôûäëïöü]+", re.IGNORECASE)
    counter = Counter()

    for line in lines:
        words = word_pattern.findall(line["content"].lower())
        # Single words
        valid_words = []
        for word in words:
            if (len(word) >= MIN_KEYWORD_LENGTH
                    and word not in STOPWORDS):
                counter[word] += 1
                valid_words.append(word)
            else:
                valid_words.append(None)  # Placeholder to maintain positions

        # Bigrams and trigrams from consecutive valid words
        _extract_ngrams(words, counter, n=2)
        _extract_ngrams(words, counter, n=3)

    # Filter by minimum frequency
    keywords = [
        term for term, count in counter.most_common()
        if count >= MIN_KEYWORD_FREQUENCY
    ]

    return keywords


def _extract_ngrams(words, counter, n=2):
    """Extract n-grams from a list of words, skipping stopwords at boundaries.

    Only creates n-grams where ALL component words are significant
    (not stopwords and meet minimum length).

    Args:
        words: List of lowercase words from a single line.
        counter: Counter to update with n-gram counts.
        n: N-gram size (2 for bigrams, 3 for trigrams).
    """
    for i in range(len(words) - n + 1):
        gram_words = words[i:i + n]
        # All words must be significant (not stopwords, sufficient length)
        if all(
            len(w) >= MIN_KEYWORD_LENGTH and w not in STOPWORDS
            for w in gram_words
        ):
            ngram = " ".join(gram_words)
            counter[ngram] += 1


def build_clean_md(source_name, source_id, sections, lines, keywords):
    """Assemble the final clean-md.json structure.

    Args:
        source_name: Original PDF filename.
        source_id: Source ID within the project.
        sections: List of section dicts.
        lines: List of line dicts.
        keywords: List of keyword strings.

    Returns:
        dict — complete clean-md.json structure.
    """
    return {
        "source": source_name,
        "source_id": source_id,
        "created": storage.now_iso(),
        "keywords": keywords,
        "sections": sections,
        "lines": lines,
        "stats": {
            "total_sections": len(sections),
            "total_lines": len(lines),
            "total_keywords": len(keywords),
        },
    }


def chunk_markdown(project_name, source_id=None):
    """Orchestrate the full chunking pipeline for a project source.

    This is the main entry point for Step 2. It:
    1. Loads raw_output.md
    2. Splits into sections
    3. Extracts lines with section assignments
    4. Extracts keywords
    5. Builds and saves clean-md.json

    Args:
        project_name: Name of the project.
        source_id: Source ID to process (None for latest).

    Returns:
        dict — the complete clean-md.json structure (also saved to disk).
    """
    # Load markdown
    md_text, source_id = load_markdown(project_name, source_id)
    console.print(f"  Loaded raw_output.md from [bold]{source_id}[/bold]")

    # Get source filename from metadata
    meta_path = storage.get_source_path(project_name, source_id, "source-meta.json")
    meta = storage.load_json(meta_path)
    source_name = meta.get("filename", "unknown.pdf")

    # Split into sections
    sections = split_into_sections(md_text)
    console.print(f"  Sections: {len(sections)}")

    # Extract lines
    lines = extract_lines(md_text, sections)
    console.print(f"  Lines: {len(lines)}")

    # Extract keywords
    keywords = extract_keywords(lines)
    console.print(f"  Keywords: {len(keywords)}")

    # Build structure
    clean_md = build_clean_md(source_name, source_id, sections, lines, keywords)

    # Save to source directory
    output_path = storage.get_source_path(project_name, source_id, "clean-md.json")
    storage.save_json(clean_md, output_path)
    console.print(f"  Saved: {output_path}")

    # Update source metadata
    if meta:
        meta["status"] = "chunked"
        storage.save_json(meta, meta_path)

    return clean_md
