"""
atenea/extract.py — Step 3: Knowledge Extraction (AI-powered)

Extracts structured knowledge from clean-md.json using an LLM:
- Points: Filtered keywords with special relevance
- Paths: CSPOJ ontological pentads (Context-Subject-Predicate-Object-Justification)
- Sets: Semantic groupings of points (no size constraint)
- Maps: Complex structures grouping 5-9 paths

Pipeline position:
    [clean-md.json] → extract.py → data.json → [generate.py]

== Token cost estimate (50-page PDF, ~10 sections) ==
    extract_points: ~25,000 tokens (~10 calls)
    extract_paths:  ~45,000 tokens (~10 calls)
    extract_sets:    ~1,500 tokens (1 call)
    extract_maps:    ~3,000 tokens (1 call)
    Total:          ~74,500 tokens → ~$0.02-0.03 with DeepSeek

== All functions accept model/temperature overrides ==
    These override the globals in config/models.py for that call only.
"""

import json
import logging
from difflib import SequenceMatcher

from rich.console import Console
from rich.progress import Progress

from atenea import ai, storage
from atenea.utils import generate_id, validate_element_count
from config import defaults, prompts, models as models_config

console = Console()
log = logging.getLogger(__name__)


# ============================================================
# POINT EXTRACTION
# ============================================================

def extract_points(clean_md, model=None, temperature=None):
    """Extract significant keywords (Points) from clean-md.json.

    Sends each section's text + candidate keywords to the LLM,
    which filters them to only those with special relevance.

    Args:
        clean_md: Dict loaded from clean-md.json.
        model: Override model (litellm format). None = use config.
        temperature: Override temperature. None = use config.

    Returns:
        list[dict] — points, each with:
            id, term, relevance_reason, score, frequency, section_ids
    """
    all_keywords = clean_md.get("keywords", [])
    sections = clean_md.get("sections", [])
    lines = clean_md.get("lines", [])

    if not all_keywords:
        console.print("[yellow]Warning: No keywords in clean-md.json[/yellow]")
        return []

    # Detect language from first section's text
    first_section_text = _get_section_text(sections[0], lines) if sections else ""
    lang = ai.detect_language(first_section_text)
    lang_instruction = ai.get_language_instruction(lang)

    # Extract points per section
    seen_terms = {}  # term -> point dict (deduplicate across sections)

    with Progress(console=console, transient=True) as progress:
        task = progress.add_task("Extracting points...", total=len(sections))

        for section in sections:
            section_text = _get_section_text(section, lines)
            if not section_text.strip():
                progress.advance(task)
                continue

            # Build prompt
            prompt = prompts.EXTRACT_POINTS_PROMPT.format(
                keywords=json.dumps(all_keywords[:100], ensure_ascii=False),
                section_title=section["title"],
                text=section_text[:4000],  # Limit to avoid token overflow
                language_instruction=lang_instruction,
            )

            try:
                result = ai.call_llm_json(
                    prompt,
                    model=model,
                    temperature=temperature,
                    task="extraction_points",
                )
            except Exception as e:
                log.warning(f"Point extraction failed for section '{section['title']}': {e}")
                progress.advance(task)
                continue

            # Process results
            if isinstance(result, list):
                for item in result:
                    term = item.get("term", "").strip().lower()
                    if not term:
                        continue
                    if term in seen_terms:
                        # Update frequency and add section
                        seen_terms[term]["frequency"] += 1
                        if section["id"] not in seen_terms[term]["section_ids"]:
                            seen_terms[term]["section_ids"].append(section["id"])
                    else:
                        seen_terms[term] = {
                            "id": generate_id("pt"),
                            "term": term,
                            "relevance_reason": item.get("relevance_reason", ""),
                            "score": 0.0,
                            "frequency": 1,
                            "section_ids": [section["id"]],
                        }

            progress.advance(task)

    points = list(seen_terms.values())
    console.print(f"  Points extracted: {len(points)}")
    return points


# ============================================================
# PATH EXTRACTION (CSPOJ)
# ============================================================

def extract_paths(clean_md, points, model=None, temperature=None):
    """Extract CSPOJ ontological paths from text using points as anchors.

    Each path is a pentad: Context-Subject-Predicate-Object-Justification.
    Each path must reference 5-9 points (7±2 rule).

    Args:
        clean_md: Dict loaded from clean-md.json.
        points: List of point dicts from extract_points().
        model: Override model. None = use config.
        temperature: Override temperature. None = use config.

    Returns:
        list[dict] — paths, each with:
            id, context, subject, predicate, object, justification,
            point_ids, retrieval_count, section_id
    """
    sections = clean_md.get("sections", [])
    lines = clean_md.get("lines", [])

    if not points:
        console.print("[yellow]Warning: No points to build paths from[/yellow]")
        return []

    # Build point lookup for the prompt
    points_summary = json.dumps(
        [{"id": p["id"], "term": p["term"]} for p in points],
        ensure_ascii=False,
    )

    # Detect language
    first_text = _get_section_text(sections[0], lines) if sections else ""
    lang = ai.detect_language(first_text)
    lang_instruction = ai.get_language_instruction(lang)

    all_paths = []

    with Progress(console=console, transient=True) as progress:
        task = progress.add_task("Extracting CSPOJ paths...", total=len(sections))

        for section in sections:
            section_text = _get_section_text(section, lines)
            if not section_text.strip():
                progress.advance(task)
                continue

            # Filter points relevant to this section
            section_points = [
                p for p in points if section["id"] in p["section_ids"]
            ]
            if not section_points:
                # Use all points as fallback
                section_points = points

            section_points_json = json.dumps(
                [{"id": p["id"], "term": p["term"]} for p in section_points],
                ensure_ascii=False,
            )

            prompt = prompts.EXTRACT_PATHS_PROMPT.format(
                points=section_points_json,
                section_title=section["title"],
                text=section_text[:6000],
                min_elements=defaults.MIN_ELEMENTS,
                max_elements=defaults.MAX_ELEMENTS,
                language_instruction=lang_instruction,
            )

            try:
                result = ai.call_llm_json(
                    prompt,
                    model=model,
                    temperature=temperature,
                    task="extraction_paths",
                )
            except Exception as e:
                log.warning(f"Path extraction failed for '{section['title']}': {e}")
                progress.advance(task)
                continue

            if isinstance(result, list):
                for item in result:
                    path = {
                        "id": generate_id("path"),
                        "context": item.get("context", ""),
                        "subject": item.get("subject", ""),
                        "predicate": item.get("predicate", ""),
                        "object": item.get("object", ""),
                        "justification": item.get("justification", ""),
                        "point_ids": item.get("point_ids", []),
                        "retrieval_count": 0,
                        "section_id": section["id"],
                    }

                    # Validate: require at least 2 point_ids (ideal: 5-9)
                    n_pts = len(path["point_ids"])
                    if n_pts < 2:
                        log.info(f"Path skipped (<2 points): {path['subject']} → {path['object']}")
                        continue
                    if n_pts < defaults.MIN_ELEMENTS:
                        log.info(f"Path accepted with {n_pts} points (ideal: {defaults.MIN_ELEMENTS}-{defaults.MAX_ELEMENTS})")

                    all_paths.append(path)

            progress.advance(task)

    console.print(f"  Paths extracted: {len(all_paths)}")
    return all_paths


# ============================================================
# SET EXTRACTION
# ============================================================

def extract_sets(points, model=None, temperature=None):
    """Group points into semantic sets.

    Sets have no size constraint (unlike paths and maps).

    Args:
        points: List of point dicts.
        model: Override model.
        temperature: Override temperature.

    Returns:
        list[dict] — sets, each with: id, name, point_ids, description
    """
    if not points:
        return []

    points_json = json.dumps(
        [{"id": p["id"], "term": p["term"]} for p in points],
        ensure_ascii=False,
    )

    # Language from first point's text (basic heuristic)
    sample_text = " ".join(p["term"] for p in points[:20])
    lang = ai.detect_language(sample_text)
    lang_instruction = ai.get_language_instruction(lang)

    prompt = prompts.EXTRACT_SETS_PROMPT.format(
        points=points_json,
        language_instruction=lang_instruction,
    )

    try:
        result = ai.call_llm_json(
            prompt, model=model, temperature=temperature, task="extraction_sets",
        )
    except Exception as e:
        log.error(f"Set extraction failed: {e}")
        return []

    sets = []
    if isinstance(result, list):
        for item in result:
            sets.append({
                "id": generate_id("set"),
                "name": item.get("name", ""),
                "point_ids": item.get("point_ids", []),
                "description": item.get("description", ""),
            })

    console.print(f"  Sets extracted: {len(sets)}")
    return sets


# ============================================================
# MAP EXTRACTION
# ============================================================

def extract_maps(paths, model=None, temperature=None):
    """Group 5-9 paths into higher-level maps.

    A map is a "path of paths" — a complex structure where some CSPOJ
    element is itself another path.

    Args:
        paths: List of path dicts.
        model: Override model.
        temperature: Override temperature.

    Returns:
        list[dict] — maps, each with: id, content, path_ids, description
    """
    if len(paths) < 2:
        console.print(
            f"  [yellow]Not enough paths ({len(paths)}) to build maps "
            f"(minimum 2)[/yellow]"
        )
        return []

    paths_json = json.dumps(
        [{
            "id": p["id"],
            "context": p["context"],
            "subject": p["subject"],
            "predicate": p["predicate"],
            "object": p["object"],
        } for p in paths],
        ensure_ascii=False,
    )

    # Language detection
    sample = " ".join(p["context"] for p in paths[:5])
    lang = ai.detect_language(sample)
    lang_instruction = ai.get_language_instruction(lang)

    prompt = prompts.EXTRACT_MAPS_PROMPT.format(
        paths=paths_json,
        min_elements=defaults.MIN_ELEMENTS,
        max_elements=defaults.MAX_ELEMENTS,
        language_instruction=lang_instruction,
    )

    try:
        result = ai.call_llm_json(
            prompt, model=model, temperature=temperature, task="extraction_maps",
        )
    except Exception as e:
        log.error(f"Map extraction failed: {e}")
        return []

    maps = []
    if isinstance(result, list):
        for item in result:
            map_item = {
                "id": generate_id("map"),
                "content": item.get("content", ""),
                "path_ids": item.get("path_ids", []),
                "description": item.get("description", ""),
            }

            n_paths = len(map_item["path_ids"])
            if n_paths < 2:
                log.info(f"Map skipped (<2 paths): {map_item['content'][:50]}")
                continue

            maps.append(map_item)

    console.print(f"  Maps extracted: {len(maps)}")
    return maps


# ============================================================
# SECOND-PASS: ORPHAN RECOVERY + MAP EXPANSION
# ============================================================

def recover_orphan_points(clean_md, points, paths, model=None, temperature=None):
    """Generate new CSPOJ paths to connect orphan/low-connectivity points.

    Identifies points referenced by 0 or 1 paths and creates new paths
    that integrate them with well-connected hub points.

    Args:
        clean_md: Dict from clean-md.json.
        points: List of point dicts (with path_ids from enrich_graph).
        paths: List of existing path dicts.
        model: Override model.
        temperature: Override temperature.

    Returns:
        list[dict] — new paths to append to the paths list.
    """
    lines = clean_md.get("lines", [])

    # Find orphan points (0-1 path references)
    path_count = {}
    for p in paths:
        for pid in p.get("point_ids", []):
            path_count[pid] = path_count.get(pid, 0) + 1

    orphans = [p for p in points if path_count.get(p["id"], 0) <= 1]
    hubs = [p for p in points if path_count.get(p["id"], 0) >= 3]

    if not orphans:
        console.print("  [dim]No orphan points to recover[/dim]")
        return []

    if not hubs:
        hubs = sorted(points, key=lambda p: path_count.get(p["id"], 0), reverse=True)[:20]

    console.print(f"  Orphan points: {len(orphans)}, Hub points: {len(hubs)}")

    # Build text from sections that contain orphan points
    orphan_sections = set()
    for op in orphans:
        orphan_sections.update(op.get("section_ids", []))

    sections = clean_md.get("sections", [])
    relevant_text = ""
    for sec in sections:
        if sec["id"] in orphan_sections:
            sec_text = _get_section_text(sec, lines)
            if sec_text.strip():
                relevant_text += f"\n### {sec['title']}\n{sec_text}\n"

    if not relevant_text.strip():
        relevant_text = "\n".join(l["content"] for l in lines[:100])

    # Detect language
    lang = ai.detect_language(relevant_text[:500])
    lang_instruction = ai.get_language_instruction(lang)

    orphan_json = json.dumps(
        [{"id": p["id"], "term": p["term"]} for p in orphans[:40]],
        ensure_ascii=False,
    )
    hub_json = json.dumps(
        [{"id": p["id"], "term": p["term"]} for p in hubs[:30]],
        ensure_ascii=False,
    )

    prompt = prompts.RECOVER_ORPHAN_PATHS_PROMPT.format(
        orphan_points=orphan_json,
        hub_points=hub_json,
        text=relevant_text[:6000],
        min_elements=defaults.MIN_ELEMENTS,
        max_elements=defaults.MAX_ELEMENTS,
        language_instruction=lang_instruction,
    )

    try:
        result = ai.call_llm_json(
            prompt, model=model, temperature=temperature,
            task="extraction_paths",
        )
    except Exception as e:
        log.warning(f"Orphan recovery failed: {e}")
        return []

    new_paths = []
    if isinstance(result, list):
        for item in result:
            path = {
                "id": generate_id("path"),
                "context": item.get("context", ""),
                "subject": item.get("subject", ""),
                "predicate": item.get("predicate", ""),
                "object": item.get("object", ""),
                "justification": item.get("justification", ""),
                "point_ids": item.get("point_ids", []),
                "retrieval_count": 0,
                "section_id": None,  # Cross-section path
                "origin": "orphan_recovery",
            }
            if len(path["point_ids"]) >= 3:
                new_paths.append(path)

    console.print(f"  Recovered: {len(new_paths)} new paths from orphan points")
    return new_paths


def expand_maps(paths, existing_maps, model=None, temperature=None):
    """Create maps for paths not covered by any existing map.

    Args:
        paths: All path dicts (with map_ids from enrich_graph).
        existing_maps: Current map dicts.
        model: Override model.
        temperature: Override temperature.

    Returns:
        list[dict] — new maps to append.
    """
    # Find unmapped paths
    mapped_ids = set()
    for m in existing_maps:
        mapped_ids.update(m.get("path_ids", []))

    unmapped = [p for p in paths if p["id"] not in mapped_ids]

    if len(unmapped) < 2:
        console.print(f"  [dim]Only {len(unmapped)} unmapped paths — skipping map expansion[/dim]")
        return []

    console.print(f"  Unmapped paths: {len(unmapped)} / {len(paths)}")

    # Detect language
    sample = " ".join(p.get("context", "") for p in unmapped[:5])
    lang = ai.detect_language(sample)
    lang_instruction = ai.get_language_instruction(lang)

    unmapped_json = json.dumps(
        [{
            "id": p["id"],
            "context": p["context"],
            "subject": p["subject"],
            "predicate": p["predicate"],
            "object": p["object"],
        } for p in unmapped],
        ensure_ascii=False,
    )

    existing_json = json.dumps(
        [{
            "map_id": m["id"],
            "content": m["content"],
            "path_ids": m["path_ids"],
        } for m in existing_maps],
        ensure_ascii=False,
    )

    prompt = prompts.EXPAND_MAPS_PROMPT.format(
        unmapped_paths=unmapped_json,
        existing_maps=existing_json,
        min_elements=defaults.MIN_ELEMENTS,
        max_elements=defaults.MAX_ELEMENTS,
        language_instruction=lang_instruction,
    )

    try:
        result = ai.call_llm_json(
            prompt, model=model, temperature=temperature,
            task="extraction_maps",
        )
    except Exception as e:
        log.warning(f"Map expansion failed: {e}")
        return []

    new_maps = []
    if isinstance(result, list):
        for item in result:
            extends = item.get("extends")
            if extends:
                # Expand existing map
                for m in existing_maps:
                    if m["id"] == extends:
                        new_ids = [pid for pid in item.get("path_ids", []) if pid not in m["path_ids"]]
                        m["path_ids"].extend(new_ids)
                        log.info(f"Expanded map {extends} with {len(new_ids)} paths")
                        break
            else:
                # New map
                map_item = {
                    "id": generate_id("map"),
                    "content": item.get("content", ""),
                    "path_ids": item.get("path_ids", []),
                    "description": item.get("description", ""),
                }
                if len(map_item["path_ids"]) >= 2:
                    new_maps.append(map_item)

    console.print(f"  New maps: {len(new_maps)}")
    return new_maps


# ============================================================
# DATA.JSON ASSEMBLY
# ============================================================

def build_data_json(source, source_id, points, paths, sets, maps, clean_md=None):
    """Assemble the complete data.json structure with graph enrichment.

    After assembling the raw structures, runs enrich_graph() to add:
    - Reverse indexes (point→paths, path→maps, set→paths)
    - Point scores (frequency × connectivity)
    - Justification line anchoring
    - Graph connectivity edges

    Args:
        source: Original PDF filename.
        source_id: Source ID.
        points, paths, sets, maps: Extracted knowledge structures.
        clean_md: Optional clean-md.json dict for line-level anchoring.

    Returns:
        dict — complete data.json with enriched graph.
    """
    data = {
        "source": source,
        "source_id": source_id,
        "created": storage.now_iso(),
        "points": points,
        "paths": paths,
        "sets": sets,
        "maps": maps,
        "stats": {
            "total_points": len(points),
            "total_paths": len(paths),
            "total_sets": len(sets),
            "total_maps": len(maps),
        },
    }

    # Enrich graph with indexes, scores, and cross-references
    enrich_graph(data, clean_md)

    return data


# ============================================================
# GRAPH ENRICHMENT (post-extraction, no LLM calls)
# ============================================================

def enrich_graph(data, clean_md=None):
    """Enrich the knowledge graph with indexes, scores, and cross-references.

    This is a purely procedural post-processing step (no LLM calls).
    It adds bidirectional traceability and connectivity metadata.

    Mutations applied to data in-place:
    1. Reverse indexes: point→paths, path→maps, set→covering_paths
    2. Point scores: frequency × connectivity normalized
    3. Justification → source line anchoring
    4. Graph edges: path↔path edges via shared points
    5. Set↔path bridge: which paths cover which sets

    Args:
        data: data.json dict (mutated in-place).
        clean_md: Optional clean-md.json dict for line anchoring.
    """
    points = data.get("points", [])
    paths = data.get("paths", [])
    sets = data.get("sets", [])
    maps = data.get("maps", [])

    point_by_id = {p["id"]: p for p in points}

    # --- 1. Reverse indexes ---
    _build_reverse_indexes(points, paths, sets, maps)

    # --- 2. Point scores ---
    _compute_point_scores(points, paths)

    # --- 3. Justification line anchoring ---
    if clean_md:
        _anchor_justifications(paths, clean_md)
        _anchor_points_to_lines(points, clean_md)

    # --- 4. Path↔path edges via shared points ---
    edges = _compute_path_edges(paths)
    data["graph_edges"] = edges

    # --- 5. Set↔path bridge ---
    _bridge_sets_paths(sets, paths)

    # --- 6. Graph connectivity stats ---
    data["graph_stats"] = _compute_graph_stats(points, paths, sets, maps, edges)

    console.print(f"  [dim]Graph enriched: {len(edges)} path edges, "
                  f"{sum(1 for p in points if p.get('path_ids'))} connected points[/dim]")


def _build_reverse_indexes(points, paths, sets, maps):
    """Add reverse references: point→paths, path→maps, point→sets."""
    # point → paths
    for p in points:
        p["path_ids"] = []
    point_by_id = {p["id"]: p for p in points}
    for path in paths:
        for pid in path.get("point_ids", []):
            if pid in point_by_id:
                point_by_id[pid]["path_ids"].append(path["id"])

    # path → maps
    for path in paths:
        path["map_ids"] = []
    path_by_id = {p["id"]: p for p in paths}
    for m in maps:
        for pid in m.get("path_ids", []):
            if pid in path_by_id:
                path_by_id[pid]["map_ids"].append(m["id"])

    # point → sets
    for p in points:
        p["set_ids"] = []
    for s in sets:
        for pid in s.get("point_ids", []):
            if pid in point_by_id:
                point_by_id[pid]["set_ids"].append(s["id"])


def _compute_point_scores(points, paths):
    """Compute point.score = normalized(frequency × connectivity).

    Score combines how often a point appears in the text (frequency)
    with how connected it is in the knowledge graph (path count).
    """
    if not points:
        return

    # Count paths per point
    path_count = {}
    for path in paths:
        for pid in path.get("point_ids", []):
            path_count[pid] = path_count.get(pid, 0) + 1

    # Raw score = frequency × (1 + path_count)
    raw_scores = []
    for p in points:
        freq = p.get("frequency", 1)
        conn = path_count.get(p["id"], 0)
        raw = freq * (1 + conn)
        raw_scores.append(raw)

    # Normalize to [0, 1]
    max_raw = max(raw_scores) if raw_scores else 1
    for p, raw in zip(points, raw_scores):
        p["score"] = round(raw / max_raw, 3) if max_raw > 0 else 0.0


def _anchor_justifications(paths, clean_md):
    """Anchor path justifications to source line numbers.

    For each path, find the lines in clean-md.json that best match
    the justification text. Stores line_numbers in the path.
    """
    lines = clean_md.get("lines", [])
    if not lines:
        return

    for path in paths:
        justification = path.get("justification", "").strip()
        if not justification:
            path["justification_lines"] = []
            continue

        just_lower = justification.lower()
        matched_lines = []
        for line in lines:
            content_lower = line["content"].lower()
            # Check if any significant portion of the line appears in justification
            # or vice versa (handles multi-line justifications)
            if len(content_lower) > 10:
                if content_lower in just_lower or just_lower[:80] in content_lower:
                    matched_lines.append(line["line_number"])

        path["justification_lines"] = matched_lines


def _anchor_points_to_lines(points, clean_md):
    """Map each point to the source lines where its term appears."""
    lines = clean_md.get("lines", [])
    if not lines:
        return

    for point in points:
        term_lower = point["term"].lower()
        matched = []
        for line in lines:
            if term_lower in line["content"].lower():
                matched.append(line["line_number"])
        point["source_lines"] = matched


def _compute_path_edges(paths):
    """Compute path↔path edges via shared points.

    Two paths are connected if they share at least one point.
    Edge weight = number of shared points.

    Returns:
        list[dict] — edges with: source, target, shared_points, weight
    """
    edges = []
    for i, p1 in enumerate(paths):
        pts1 = set(p1.get("point_ids", []))
        for p2 in paths[i + 1:]:
            pts2 = set(p2.get("point_ids", []))
            shared = pts1 & pts2
            if shared:
                edges.append({
                    "source": p1["id"],
                    "target": p2["id"],
                    "shared_points": list(shared),
                    "weight": len(shared),
                })
    return edges


def _bridge_sets_paths(sets, paths):
    """Link sets to paths that cover their points.

    A path 'covers' a set if it references at least one point from that set.
    """
    for s in sets:
        set_points = set(s.get("point_ids", []))
        covering = []
        for path in paths:
            path_points = set(path.get("point_ids", []))
            overlap = set_points & path_points
            if overlap:
                covering.append({
                    "path_id": path["id"],
                    "overlap_count": len(overlap),
                    "overlap_ratio": round(len(overlap) / max(len(set_points), 1), 3),
                })
        # Sort by overlap ratio descending
        covering.sort(key=lambda x: x["overlap_ratio"], reverse=True)
        s["covering_paths"] = covering


def _compute_graph_stats(points, paths, sets, maps, edges):
    """Compute graph-level connectivity statistics."""
    # Point connectivity distribution
    path_count_per_point = {}
    for path in paths:
        for pid in path.get("point_ids", []):
            path_count_per_point[pid] = path_count_per_point.get(pid, 0) + 1

    orphan_points = sum(1 for p in points if p["id"] not in path_count_per_point)
    single_ref = sum(1 for c in path_count_per_point.values() if c == 1)
    multi_ref = sum(1 for c in path_count_per_point.values() if c >= 2)
    hub_points = sum(1 for c in path_count_per_point.values() if c >= 10)

    # Path connectivity
    paths_in_maps = sum(1 for p in paths if p.get("map_ids"))
    isolated_paths = sum(1 for p in paths if not p.get("map_ids"))

    # Set coverage
    sets_with_paths = sum(1 for s in sets if s.get("covering_paths"))

    return {
        "point_distribution": {
            "orphan": orphan_points,
            "single_ref": single_ref,
            "multi_ref": multi_ref,
            "hub (10+)": hub_points,
        },
        "path_coverage": {
            "in_maps": paths_in_maps,
            "isolated": isolated_paths,
            "total_edges": len(edges),
            "avg_edges_per_path": round(2 * len(edges) / max(len(paths), 1), 1),
        },
        "set_bridge": {
            "sets_with_paths": sets_with_paths,
            "total_sets": len(sets),
        },
    }


# ============================================================
# CONFIDENCE METRICS
# ============================================================

def compute_extraction_stats(data, clean_md):
    """Compute confidence metrics for the extraction.

    Metrics:
    1. Keyword coverage: keywords_in_paths / total_keywords
    2. Section coverage: sections_with_paths / total_sections
    3. Justification verification: paths with verbatim justification / total
    4. Path density: paths per section
    5. Point connectivity: points in ≥2 paths / total points

    Args:
        data: Dict from data.json.
        clean_md: Dict from clean-md.json.

    Returns:
        dict — metrics with values and targets.
    """
    points = data.get("points", [])
    paths = data.get("paths", [])
    sections = clean_md.get("sections", [])
    lines = clean_md.get("lines", [])
    keywords = clean_md.get("keywords", [])

    # 1. Keyword coverage (with fuzzy matching for compound terms)
    point_terms = {p["term"].lower() for p in points}
    keywords_covered = 0
    for kw in keywords:
        kw_lower = kw.lower()
        # Exact match first
        if kw_lower in point_terms:
            keywords_covered += 1
            continue
        # Fuzzy: check if keyword is a substring of any point term or vice versa
        matched = False
        for pt in point_terms:
            if kw_lower in pt or pt in kw_lower:
                matched = True
                break
            # Sequence similarity for close matches (threshold 0.8)
            if SequenceMatcher(None, kw_lower, pt).ratio() >= 0.8:
                matched = True
                break
        if matched:
            keywords_covered += 1
    keyword_coverage = keywords_covered / max(len(keywords), 1)

    # 2. Section coverage
    sections_with_paths = set()
    for path in paths:
        if path.get("section_id"):
            sections_with_paths.add(path["section_id"])
    section_coverage = len(sections_with_paths) / max(len(sections), 1)

    # 3. Justification verification (check if verbatim in source text)
    all_text = " ".join(l["content"] for l in lines).lower()
    verified = 0
    for path in paths:
        justification = path.get("justification", "").lower().strip()
        if justification and justification[:50] in all_text:
            verified += 1
    justification_rate = verified / max(len(paths), 1)

    # 4. Path density
    path_density = len(paths) / max(len(sections), 1)

    # 5. Point connectivity
    point_path_count = {}
    for path in paths:
        for pid in path.get("point_ids", []):
            point_path_count[pid] = point_path_count.get(pid, 0) + 1
    connected = sum(1 for c in point_path_count.values() if c >= 2)
    connectivity = connected / max(len(points), 1)

    # 6. 7±2 compliance: paths with MIN_ELEMENTS-MAX_ELEMENTS point_ids
    compliant = sum(
        1 for p in paths
        if defaults.MIN_ELEMENTS <= len(p.get("point_ids", [])) <= defaults.MAX_ELEMENTS
    )
    compliance_rate = compliant / max(len(paths), 1)

    # 7. Justification anchoring rate (paths anchored to source lines)
    anchored = sum(1 for p in paths if p.get("justification_lines"))
    anchor_rate = anchored / max(len(paths), 1)

    # 8. Point traceability (points traced to source lines)
    traced_points = sum(1 for p in points if p.get("source_lines"))
    trace_rate = traced_points / max(len(points), 1)

    # 9. Map coverage (paths that belong to at least one map)
    mapped_paths = sum(1 for p in paths if p.get("map_ids"))
    map_coverage = mapped_paths / max(len(paths), 1)

    # 10. Set-path bridge (sets with at least one covering path)
    bridged_sets = sum(1 for s in data.get("sets", []) if s.get("covering_paths"))
    set_bridge_rate = bridged_sets / max(len(data.get("sets", [])), 1)

    stats = {
        "keyword_coverage": {
            "value": round(keyword_coverage, 3),
            "target": 0.85,
            "status": "good" if keyword_coverage >= 0.85 else "low",
        },
        "section_coverage": {
            "value": round(section_coverage, 3),
            "target": 1.0,
            "status": "good" if section_coverage >= 0.9 else "low",
        },
        "justification_verbatim_rate": {
            "value": round(justification_rate, 3),
            "target": 0.95,
            "status": "good" if justification_rate >= 0.95 else "low",
        },
        "path_density_per_section": {
            "value": round(path_density, 2),
            "expected_range": "3-15",
        },
        "point_connectivity": {
            "value": round(connectivity, 3),
            "target": 0.60,
            "status": "good" if connectivity >= 0.60 else "low",
        },
        "7pm2_compliance": {
            "value": round(compliance_rate, 3),
            "target": 0.50,
            "status": "good" if compliance_rate >= 0.50 else "low",
            "detail": f"{compliant}/{len(paths)} paths have {defaults.MIN_ELEMENTS}-{defaults.MAX_ELEMENTS} point_ids",
        },
        "justification_anchoring": {
            "value": round(anchor_rate, 3),
            "target": 0.80,
            "status": "good" if anchor_rate >= 0.80 else "low",
            "detail": f"{anchored}/{len(paths)} paths anchored to source lines",
        },
        "point_traceability": {
            "value": round(trace_rate, 3),
            "target": 0.90,
            "status": "good" if trace_rate >= 0.90 else "low",
            "detail": f"{traced_points}/{len(points)} points traced to source lines",
        },
        "map_coverage": {
            "value": round(map_coverage, 3),
            "target": 0.70,
            "status": "good" if map_coverage >= 0.70 else "low",
            "detail": f"{mapped_paths}/{len(paths)} paths in maps",
        },
        "set_path_bridge": {
            "value": round(set_bridge_rate, 3),
            "target": 1.0,
            "status": "good" if set_bridge_rate >= 0.90 else "low",
            "detail": f"{bridged_sets}/{len(data.get('sets', []))} sets with covering paths",
        },
    }

    return stats


# ============================================================
# ORCHESTRATOR
# ============================================================

def run_extraction(project_name, source_id=None, model=None):
    """Run the full extraction pipeline for a project source.

    Orchestrates: load clean-md → extract points → paths → sets → maps
    → build data.json → save.

    Args:
        project_name: Name of the project.
        source_id: Source to extract from (None for latest).
        model: Override model for all extraction steps.

    Returns:
        dict — the complete data.json structure (also saved to disk).
    """
    # Find source
    if source_id is None:
        sources = storage.list_sources(project_name)
        if not sources:
            raise FileNotFoundError(f"No sources in project '{project_name}'")
        source_id = sources[-1]

    # Load clean-md.json
    clean_md_path = storage.get_source_path(project_name, source_id, "clean-md.json")
    clean_md = storage.load_json(clean_md_path)
    if not clean_md:
        raise FileNotFoundError(
            f"No clean-md.json for source {source_id}. Run 'atenea chunk' first."
        )

    source_name = clean_md.get("source", "unknown.pdf")
    console.print(f"  Extracting from [bold]{source_id}[/bold]: {source_name}")

    # Run extraction pipeline
    console.print("\n[bold]Step 3a:[/bold] Extracting points...")
    points = extract_points(clean_md, model=model)

    console.print("\n[bold]Step 3b:[/bold] Extracting CSPOJ paths...")
    paths = extract_paths(clean_md, points, model=model)

    console.print("\n[bold]Step 3c:[/bold] Extracting semantic sets...")
    sets = extract_sets(points, model=model)

    console.print("\n[bold]Step 3d:[/bold] Extracting maps...")
    maps = extract_maps(paths, model=model)

    # First build to get graph enrichment (reverse indexes needed for second pass)
    data = build_data_json(source_name, source_id, points, paths, sets, maps, clean_md=clean_md)

    # --- Second pass: orphan recovery + map expansion ---
    console.print("\n[bold]Step 3e:[/bold] Recovering orphan points...")
    new_paths = recover_orphan_points(clean_md, points, paths, model=model)
    if new_paths:
        paths.extend(new_paths)

    console.print("\n[bold]Step 3f:[/bold] Expanding map coverage...")
    new_maps = expand_maps(paths, maps, model=model)
    if new_maps:
        maps.extend(new_maps)

    # Rebuild with enriched data
    data = build_data_json(source_name, source_id, points, paths, sets, maps, clean_md=clean_md)

    # Save to source directory
    data_path = storage.get_source_path(project_name, source_id, "data.json")
    storage.save_json(data, data_path)

    # Also save/merge to project-level data.json
    project_data_path = storage.get_project_path(project_name, "data.json")
    storage.save_json(data, project_data_path)

    # Compute and display stats
    stats = compute_extraction_stats(data, clean_md)
    data["extraction_stats"] = stats
    storage.save_json(data, data_path)
    storage.save_json(data, project_data_path)

    _display_stats(stats)

    # Update source metadata
    meta_path = storage.get_source_path(project_name, source_id, "source-meta.json")
    meta = storage.load_json(meta_path)
    if meta:
        meta["status"] = "extracted"
        meta["cspoj_path_count"] = len(paths)
        storage.save_json(meta, meta_path)

    return data


# ============================================================
# HELPERS
# ============================================================

def _get_section_text(section, lines):
    """Get the text content of a section by joining its lines.

    Args:
        section: Section dict with 'id'.
        lines: List of line dicts from clean-md.json.

    Returns:
        str — concatenated text of all lines in this section.
    """
    section_lines = [
        l["content"] for l in lines
        if section["id"] in l.get("section_ids", [])
    ]
    return "\n".join(section_lines)


def _display_stats(stats):
    """Display extraction confidence metrics in the terminal."""
    from rich.table import Table

    table = Table(title="Extraction Confidence Metrics")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Target", justify="right")
    table.add_column("Status")

    for name, metric in stats.items():
        value = str(metric.get("value", ""))
        target = str(metric.get("target", metric.get("expected_range", "")))
        status = metric.get("status", "")
        style = "green" if status == "good" else "yellow" if status == "low" else ""
        table.add_row(name, value, target, f"[{style}]{status}[/{style}]" if style else "")

    console.print(table)
