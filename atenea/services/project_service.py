"""
atenea/services/project_service.py — Project stats and data (UI-agnostic)

Pure functions for:
- Listing projects with computed stats
- Getting project overview data
- Building knowledge graph data for visualization

No display imports. Returns data structures for any frontend to render.
"""

from atenea import storage


def list_projects_with_stats():
    """List all projects with computed stats.

    Returns:
        list[dict]: Each dict has:
            name, n_sources, n_knowledge, n_questions,
            known, total, coverage_pct (int|None), last_sync
    """
    projects = []
    for name in storage.list_projects():
        projects.append(get_project_overview(name))
    return projects


def get_project_overview(project):
    """Get comprehensive stats for a single project.

    Returns:
        dict: {
            name, n_sources, n_knowledge, n_questions,
            known, total, coverage_pct (int|None), last_sync,
            has_knowledge, has_questions, has_coverage
        }
    """
    pdata = storage.load_json(
        str(storage.get_project_path(project, "project.json"))
    ) or {}

    n_sources = len(storage.list_sources(project))

    # Knowledge stats
    knowledge = storage.load_json(
        str(storage.get_project_path(project, "knowledge.json"))
    )
    n_kw = len(knowledge.get("keywords", [])) if knowledge else 0
    n_as = len(knowledge.get("associations", [])) if knowledge else 0
    n_sq = len(knowledge.get("sequences", [])) if knowledge else 0
    n_knowledge = n_kw + n_as + n_sq

    # Questions stats
    questions = storage.load_json(
        str(storage.get_project_path(project, "questions.json"))
    )
    if isinstance(questions, dict):
        n_questions = len(questions.get("questions", []))
    elif isinstance(questions, list):
        n_questions = len(questions)
    else:
        n_questions = 0

    # Coverage stats
    coverage = storage.load_json(
        str(storage.get_project_path(project, "coverage.json"))
    ) or {}
    items = coverage.get("items", {})
    known = sum(1 for v in items.values() if v.get("status") == "known")
    total = len(items) if items else 0
    coverage_pct = int(known / total * 100) if total > 0 else None

    last_sync = pdata.get("last_sync", "never")

    return {
        "name": project,
        "n_sources": n_sources,
        "n_knowledge": n_knowledge,
        "n_keywords": n_kw,
        "n_associations": n_as,
        "n_sequences": n_sq,
        "n_questions": n_questions,
        "known": known,
        "total": total,
        "coverage_pct": coverage_pct,
        "last_sync": last_sync,
        "has_knowledge": n_knowledge > 0,
        "has_questions": n_questions > 0,
        "has_coverage": total > 0,
    }


def get_knowledge_graph_data(project):
    """Build knowledge graph data for visualization.

    Reads knowledge.json + coverage.json to produce a graph structure
    with nodes (keywords), edges (associations), and chains (sequences).

    Returns:
        dict: {
            "nodes": [{"id", "term", "definition", "status", "tags", "source", "n_connections"}],
            "edges": [{"source", "target", "relation", "description"}],
            "sequences": [{"nodes": [...], "description"}],
            "categories": [{"name": tag}],
            "stats": {"n_nodes", "n_edges", "n_sequences", "hub_terms": [...]}
        }
    """
    knowledge = storage.load_json(
        str(storage.get_project_path(project, "knowledge.json"))
    )
    if not knowledge:
        return {"nodes": [], "edges": [], "sequences": [], "categories": [], "stats": {}}

    coverage = storage.load_json(
        str(storage.get_project_path(project, "coverage.json"))
    ) or {}
    cov_items = coverage.get("items", {})

    # Build connection count per term
    connection_count = {}
    for assoc in knowledge.get("associations", []):
        ft = assoc.get("from_term", "")
        tt = assoc.get("to_term", "")
        connection_count[ft] = connection_count.get(ft, 0) + 1
        connection_count[tt] = connection_count.get(tt, 0) + 1

    # Nodes from keywords
    nodes = []
    all_tags = set()
    known_terms = set()
    for kw in knowledge.get("keywords", []):
        term = kw.get("term", "")
        known_terms.add(term)
        tags = kw.get("tags", [])
        all_tags.update(tags)

        # SM-2 status from coverage
        cov = cov_items.get(term, {})
        status = cov.get("status", "unknown")

        nodes.append({
            "id": kw.get("id", term),
            "term": term,
            "definition": kw.get("definition", ""),
            "status": status,
            "tags": tags,
            "source": kw.get("source", ""),
            "page": kw.get("page"),
            "n_connections": connection_count.get(term, 0),
            "sm2": {
                "ef": cov.get("ef"),
                "interval": cov.get("interval"),
                "reviews": cov.get("reviews", 0),
                "correct": cov.get("correct", 0),
            } if cov else None,
        })

    # Inferred nodes: terms referenced in associations but not in keywords
    for assoc in knowledge.get("associations", []):
        for term_key in ("from_term", "to_term"):
            term = assoc.get(term_key, "")
            if term and term not in known_terms:
                known_terms.add(term)
                cov = cov_items.get(term, {})
                nodes.append({
                    "id": term,
                    "term": term,
                    "definition": "",
                    "status": cov.get("status", "unknown"),
                    "tags": [],
                    "source": assoc.get("source", ""),
                    "page": assoc.get("page"),
                    "n_connections": connection_count.get(term, 0),
                    "sm2": {
                        "ef": cov.get("ef"),
                        "interval": cov.get("interval"),
                        "reviews": cov.get("reviews", 0),
                        "correct": cov.get("correct", 0),
                    } if cov else None,
                })

    # Also check sequence nodes
    for seq in knowledge.get("sequences", []):
        for term in seq.get("nodes", []):
            if term and term not in known_terms:
                known_terms.add(term)
                cov = cov_items.get(term, {})
                nodes.append({
                    "id": term,
                    "term": term,
                    "definition": "",
                    "status": cov.get("status", "unknown"),
                    "tags": [],
                    "source": "",
                    "page": None,
                    "n_connections": connection_count.get(term, 0),
                    "sm2": None,
                })

    # Edges from associations
    edges = []
    for assoc in knowledge.get("associations", []):
        edges.append({
            "source": assoc.get("from_term", ""),
            "target": assoc.get("to_term", ""),
            "relation": assoc.get("relation", ""),
            "description": assoc.get("description", ""),
            "justification": assoc.get("justification", ""),
            "page": assoc.get("page"),
        })

    # Sequences
    sequences = []
    for seq in knowledge.get("sequences", []):
        sequences.append({
            "nodes": seq.get("nodes", []),
            "description": seq.get("description", ""),
            "pages": seq.get("pages", []),
        })

    # Categories from tags
    categories = [{"name": tag} for tag in sorted(all_tags)]

    # Hub terms (top 5 most connected)
    hub_terms = sorted(connection_count.items(), key=lambda x: -x[1])[:5]

    return {
        "nodes": nodes,
        "edges": edges,
        "sequences": sequences,
        "categories": categories,
        "stats": {
            "n_nodes": len(nodes),
            "n_edges": len(edges),
            "n_sequences": len(sequences),
            "hub_terms": [{"term": t, "connections": c} for t, c in hub_terms],
        },
    }
