"""
atenea/services/review_service.py — Coverage analysis (UI-agnostic)

Pure functions for:
- Computing coverage statistics
- Detecting knowledge gaps
- Session history retrieval

No display imports. Returns data structures for any frontend to render.
"""

from atenea import storage


def compute_coverage(project):
    """Compute coverage statistics from knowledge.json + coverage.json.

    Returns:
        dict: {
            "summary": {type: {"total", "known", "testing", "unknown"}},
            "by_source": {source: {"total", "known", "testing", "unknown"}},
            "overall": {"total", "seen", "known", "seen_pct", "known_pct"}
        }
    """
    knowledge_path = str(storage.get_project_path(project, "knowledge.json"))
    coverage_path = str(storage.get_project_path(project, "coverage.json"))

    knowledge = storage.load_json(knowledge_path)
    coverage = storage.load_json(coverage_path) or {"items": {}}
    items = coverage.get("items", {})

    summary = {}
    by_source = {}

    for item_type in ["keywords", "associations", "sequences"]:
        type_items = knowledge.get(item_type, []) if knowledge else []
        total = len(type_items)
        known = testing = unknown = 0

        for item in type_items:
            key = item.get("term", item.get("id", ""))
            status = items.get(key, {}).get("status", "unknown")

            if status == "known":
                known += 1
            elif status == "testing":
                testing += 1
            else:
                unknown += 1

            source = item.get("source", "unknown")
            src_data = by_source.setdefault(source, {
                "total": 0, "known": 0, "testing": 0, "unknown": 0
            })
            src_data["total"] += 1
            src_data[status if status in ("known", "testing") else "unknown"] += 1

        summary[item_type] = {
            "total": total,
            "known": known,
            "testing": testing,
            "unknown": unknown,
        }

    # Overall stats
    all_total = sum(d["total"] for d in summary.values())
    all_seen = sum(d["known"] + d["testing"] for d in summary.values())
    all_known = sum(d["known"] for d in summary.values())

    overall = {
        "total": all_total,
        "seen": all_seen,
        "known": all_known,
        "seen_pct": round(all_seen / all_total * 100) if all_total > 0 else 0,
        "known_pct": round(all_known / all_total * 100) if all_total > 0 else 0,
    }

    return {"summary": summary, "by_source": by_source, "overall": overall}


def detect_gaps(project):
    """Identify weak areas from coverage data.

    Returns items that have been reviewed but have low success rates.

    Returns:
        list[dict]: Sorted by worst performance. Each has:
            term, reviews, correct, ratio, ef
    """
    coverage_path = str(storage.get_project_path(project, "coverage.json"))
    coverage = storage.load_json(coverage_path) or {"items": {}}
    items = coverage.get("items", {})

    gaps = []
    for term, data in items.items():
        reviews = data.get("reviews", 0)
        correct = data.get("correct", 0)
        if reviews >= 2 and correct / reviews < 0.5:
            gaps.append({
                "term": term,
                "reviews": reviews,
                "correct": correct,
                "ratio": round(correct / reviews * 100, 1),
                "ef": data.get("ef", 0),
            })

    gaps.sort(key=lambda x: x["ratio"])
    return gaps


def get_session_history(project):
    """Get test session history.

    Returns:
        list[dict]: Sessions sorted by date. Each has:
            date, total, correct, score
    """
    sessions_path = str(storage.get_project_path(project, "sessions.json"))
    data = storage.load_json(sessions_path) or {"sessions": []}
    sessions = data.get("sessions", [])

    # Return summary without full results (lighter for display)
    return [
        {
            "date": s.get("date", ""),
            "total": s.get("total", 0),
            "correct": s.get("correct", 0),
            "score": s.get("score", 0),
        }
        for s in sessions
    ]
