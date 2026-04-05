"""
tests/test_review_service.py — Coverage analysis and gap detection tests.

Tests compute_coverage(), detect_gaps(), get_session_history()
from review_service.py.
"""

from atenea.services.review_service import (
    compute_coverage,
    detect_gaps,
    get_session_history,
)


# ============================================================
# compute_coverage
# ============================================================

class TestComputeCoverage:

    def test_counts_by_type(self, sample_project):
        result = compute_coverage(sample_project)
        kw = result["summary"]["keywords"]
        assert kw["total"] == 5
        assert kw["known"] == 1   # hipertension
        assert kw["testing"] == 1  # diabetes
        assert kw["unknown"] == 3  # insulina, estatinas, metformina

    def test_associations_counted(self, sample_project):
        result = compute_coverage(sample_project)
        assoc = result["summary"]["associations"]
        assert assoc["total"] == 2

    def test_sequences_counted(self, sample_project):
        result = compute_coverage(sample_project)
        seq = result["summary"]["sequences"]
        assert seq["total"] == 1

    def test_overall_stats(self, sample_project):
        result = compute_coverage(sample_project)
        o = result["overall"]
        # 5 keywords + 2 associations + 1 sequence = 8 total
        assert o["total"] == 8
        # known: hipertension keyword = 1
        # testing: diabetes keyword = 1
        # seen = known + testing = 2
        assert o["seen"] == 2
        assert o["known"] == 1
        assert o["seen_pct"] == 25   # 2/8 = 25%
        assert o["known_pct"] == 12  # 1/8 = 12.5 → round half to even = 12

    def test_by_source_breakdown(self, sample_project):
        result = compute_coverage(sample_project)
        by_src = result["by_source"]
        assert "doc1" in by_src
        assert "doc2" in by_src
        # doc1 has: hipertension(known), diabetes(testing), 1 association
        assert by_src["doc1"]["total"] >= 2

    def test_empty_project(self, tmp_data_dir):
        """Project with no knowledge.json returns zeros."""
        import os, json
        p = os.path.join(tmp_data_dir, "empty")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "project.json"), "w") as f:
            json.dump({"name": "empty"}, f)

        result = compute_coverage("empty")
        assert result["overall"]["total"] == 0
        assert result["overall"]["known_pct"] == 0


# ============================================================
# detect_gaps
# ============================================================

class TestDetectGaps:

    def test_detects_weak_items(self, sample_project):
        """diabetes has 2 reviews, 1 correct = 50% → exactly at boundary."""
        gaps = detect_gaps(sample_project)
        # 50% is NOT < 50%, so diabetes should NOT be a gap
        terms = [g["term"] for g in gaps]
        assert "diabetes" not in terms

    def test_detects_below_50pct(self, tmp_data_dir):
        """Item with 2 reviews, 0 correct = 0% → gap."""
        import os, json
        p = os.path.join(tmp_data_dir, "gaptest")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "project.json"), "w") as f:
            json.dump({"name": "gaptest"}, f)
        with open(os.path.join(p, "coverage.json"), "w") as f:
            json.dump({"items": {
                "weak": {"ef": 1.5, "interval": 1.0, "reviews": 3, "correct": 1, "status": "testing"},
                "strong": {"ef": 2.5, "interval": 6.0, "reviews": 5, "correct": 5, "status": "known"},
                "new": {"ef": 2.5, "interval": 1.0, "reviews": 1, "correct": 0, "status": "testing"},
            }}, f)

        gaps = detect_gaps("gaptest")
        terms = [g["term"] for g in gaps]
        assert "weak" in terms       # 1/3 = 33% < 50%
        assert "strong" not in terms  # 5/5 = 100%
        assert "new" not in terms     # only 1 review, needs ≥2

    def test_sorted_by_worst(self, tmp_data_dir):
        import os, json
        p = os.path.join(tmp_data_dir, "sorttest")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "project.json"), "w") as f:
            json.dump({"name": "sorttest"}, f)
        with open(os.path.join(p, "coverage.json"), "w") as f:
            json.dump({"items": {
                "bad": {"ef": 1.3, "interval": 1.0, "reviews": 4, "correct": 0, "status": "testing"},
                "mediocre": {"ef": 1.8, "interval": 1.0, "reviews": 4, "correct": 1, "status": "testing"},
            }}, f)

        gaps = detect_gaps("sorttest")
        assert len(gaps) == 2
        assert gaps[0]["term"] == "bad"       # 0% first
        assert gaps[1]["term"] == "mediocre"  # 25% second

    def test_gap_fields(self, tmp_data_dir):
        import os, json
        p = os.path.join(tmp_data_dir, "fields")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "project.json"), "w") as f:
            json.dump({"name": "fields"}, f)
        with open(os.path.join(p, "coverage.json"), "w") as f:
            json.dump({"items": {
                "x": {"ef": 1.5, "interval": 1.0, "reviews": 4, "correct": 1, "status": "testing"},
            }}, f)

        gaps = detect_gaps("fields")
        g = gaps[0]
        assert g["term"] == "x"
        assert g["reviews"] == 4
        assert g["correct"] == 1
        assert g["ratio"] == 25.0
        assert g["ef"] == 1.5

    def test_no_coverage_returns_empty(self, tmp_data_dir):
        import os, json
        p = os.path.join(tmp_data_dir, "nocover")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "project.json"), "w") as f:
            json.dump({"name": "nocover"}, f)

        gaps = detect_gaps("nocover")
        assert gaps == []


# ============================================================
# get_session_history
# ============================================================

class TestGetSessionHistory:

    def test_returns_sessions(self, sample_project):
        history = get_session_history(sample_project)
        assert len(history) == 2
        assert history[0]["score"] == 60.0
        assert history[1]["score"] == 80.0

    def test_session_fields(self, sample_project):
        history = get_session_history(sample_project)
        s = history[0]
        assert "date" in s
        assert "total" in s
        assert "correct" in s
        assert "score" in s
        # Should NOT include full results (lightweight)
        assert "results" not in s

    def test_no_sessions_returns_empty(self, tmp_data_dir):
        import os, json
        p = os.path.join(tmp_data_dir, "nosess")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "project.json"), "w") as f:
            json.dump({"name": "nosess"}, f)

        history = get_session_history("nosess")
        assert history == []
