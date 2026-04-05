"""
tests/test_test_service.py — Test service logic tests.

Tests evaluate_answer(), select_questions(), update_coverage(),
prepare_test(), finish_test() from test_service.py.
"""

import json
import os

from atenea.services.test_service import (
    evaluate_answer,
    select_questions,
    update_coverage,
    prepare_test,
    finish_test,
    write_session,
    build_session_summary,
    get_recent_question_ids,
)


# ============================================================
# evaluate_answer
# ============================================================

class TestEvaluateAnswer:

    def _q(self, correct="B"):
        return {
            "correct": correct,
            "options": {"A": "Opcion A", "B": "Opcion B", "C": "Opcion C", "D": "Opcion D", "E": "Opcion E"},
            "justification": "Porque B es correcto.",
        }

    def test_correct_answer(self):
        r = evaluate_answer(self._q("B"), "B")
        assert r["is_correct"] is True
        assert r["correct_answer"] == "B"
        assert r["correct_text"] == "Opcion B"
        assert r["justification"] == "Porque B es correcto."

    def test_incorrect_answer(self):
        r = evaluate_answer(self._q("B"), "A")
        assert r["is_correct"] is False
        assert r["correct_answer"] == "B"

    def test_case_sensitive(self):
        """Answer comparison is exact — 'b' != 'B'."""
        r = evaluate_answer(self._q("B"), "b")
        assert r["is_correct"] is False

    def test_all_options_can_be_correct(self):
        for letter in "ABCDE":
            r = evaluate_answer(self._q(letter), letter)
            assert r["is_correct"] is True

    def test_missing_justification(self):
        q = {"correct": "A", "options": {"A": "X"}}
        r = evaluate_answer(q, "A")
        assert r["justification"] == ""

    def test_missing_correct_text(self):
        q = {"correct": "Z", "options": {"A": "X"}}
        r = evaluate_answer(q, "A")
        assert r["correct_text"] == ""


# ============================================================
# select_questions
# ============================================================

class TestSelectQuestions:

    def _questions(self, targets_list):
        """Build question list from list of target lists."""
        return [
            {"id": f"q{i}", "targets": t, "question": f"Q{i}"}
            for i, t in enumerate(targets_list)
        ]

    def test_selects_up_to_n(self):
        qs = self._questions([["a"], ["b"], ["c"], ["d"], ["e"]])
        result = select_questions(qs, {"items": {}}, n=3)
        assert len(result) == 3

    def test_selects_all_if_fewer_than_n(self):
        qs = self._questions([["a"], ["b"]])
        result = select_questions(qs, {"items": {}}, n=10)
        assert len(result) == 2

    def test_prioritizes_unknown_over_testing(self):
        qs = self._questions([["known_item"], ["testing_item"], ["unknown_item"]])
        coverage = {"items": {
            "known_item": {"status": "known"},
            "testing_item": {"status": "testing"},
            # unknown_item not in items → unknown
        }}
        result = select_questions(qs, coverage, n=1)
        assert result[0]["targets"] == ["unknown_item"]

    def test_prioritizes_testing_over_known(self):
        qs = self._questions([["known_item"], ["testing_item"]])
        coverage = {"items": {
            "known_item": {"status": "known"},
            "testing_item": {"status": "testing"},
        }}
        result = select_questions(qs, coverage, n=1)
        assert result[0]["targets"] == ["testing_item"]

    def test_empty_questions_returns_empty(self):
        result = select_questions([], {"items": {}}, n=5)
        assert result == []

    def test_empty_coverage_treats_all_as_unknown(self):
        qs = self._questions([["a"], ["b"], ["c"]])
        result = select_questions(qs, {}, n=3)
        assert len(result) == 3

    def test_result_is_shuffled(self):
        """With enough items, order should vary (probabilistic but reliable)."""
        qs = self._questions([[f"item{i}"] for i in range(50)])
        orders = set()
        for _ in range(10):
            result = select_questions(qs, {"items": {}}, n=50)
            orders.add(tuple(q["id"] for q in result))
        # At least 2 different orderings in 10 runs
        assert len(orders) > 1


# ============================================================
# update_coverage
# ============================================================

class TestUpdateCoverage:

    def test_correct_answer_creates_item(self):
        coverage = {"items": {}}
        update_coverage(coverage, ["new_term"], is_correct=True)
        item = coverage["items"]["new_term"]
        assert item["reviews"] == 1
        assert item["correct"] == 1
        assert item["status"] == "testing"

    def test_incorrect_answer_creates_item(self):
        coverage = {"items": {}}
        update_coverage(coverage, ["new_term"], is_correct=False)
        item = coverage["items"]["new_term"]
        assert item["reviews"] == 1
        assert item["correct"] == 0

    def test_updates_multiple_targets(self):
        coverage = {"items": {}}
        update_coverage(coverage, ["term_a", "term_b"], is_correct=True)
        assert "term_a" in coverage["items"]
        assert "term_b" in coverage["items"]

    def test_updates_existing_item(self):
        coverage = {"items": {
            "term": {"ef": 2.5, "interval": 1.0, "reviews": 1, "correct": 1, "status": "testing"},
        }}
        update_coverage(coverage, ["term"], is_correct=True)
        assert coverage["items"]["term"]["reviews"] == 2
        assert coverage["items"]["term"]["correct"] == 2

    def test_correct_uses_quality_4(self):
        """Correct → quality=4, which keeps EF stable (delta=0)."""
        coverage = {"items": {}}
        update_coverage(coverage, ["t"], is_correct=True)
        assert coverage["items"]["t"]["ef"] == 2.5  # unchanged at quality=4

    def test_incorrect_uses_quality_1(self):
        """Incorrect → quality=1, which decreases EF."""
        coverage = {"items": {}}
        update_coverage(coverage, ["t"], is_correct=False)
        assert coverage["items"]["t"]["ef"] < 2.5

    def test_empty_targets_noop(self):
        coverage = {"items": {}}
        update_coverage(coverage, [], is_correct=True)
        assert coverage["items"] == {}


# ============================================================
# prepare_test (integration — uses sample_project fixture)
# ============================================================

class TestPrepareTest:

    def test_loads_questions_and_coverage(self, sample_project):
        result = prepare_test(sample_project, n=3)
        assert "questions" in result
        assert "coverage" in result
        assert len(result["questions"]) == 3

    def test_raises_if_no_questions(self, tmp_data_dir):
        # Create project with no questions
        p = os.path.join(tmp_data_dir, "empty")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "project.json"), "w") as f:
            json.dump({"name": "empty"}, f)

        import pytest
        with pytest.raises(ValueError, match="No questions"):
            prepare_test("empty")

    def test_respects_n_parameter(self, sample_project):
        r1 = prepare_test(sample_project, n=1)
        r6 = prepare_test(sample_project, n=100)
        assert len(r1["questions"]) == 1
        assert len(r6["questions"]) == 6  # only 6 exist


# ============================================================
# finish_test (integration — writes to disk)
# ============================================================

class TestFinishTest:

    def test_saves_coverage_and_session(self, sample_project):
        coverage = {"items": {"x": {"ef": 2.5, "interval": 1.0, "reviews": 1, "correct": 1, "status": "testing"}}}
        results = [{"question_id": "q1", "answer": "A", "correct": True, "targets": ["x"]}]

        session = finish_test(sample_project, results, coverage)
        assert session["total"] == 1
        assert session["correct"] == 1
        assert session["score"] == 100.0

    def test_empty_results_returns_zero(self, sample_project):
        coverage = {"items": {}}
        session = finish_test(sample_project, [], coverage)
        assert session["total"] == 0
        assert session["score"] == 0

    def test_session_persists_to_disk(self, sample_project):
        from atenea import storage
        coverage = {"items": {}}
        results = [{"question_id": "q1", "answer": "B", "correct": True, "targets": ["t"]}]
        finish_test(sample_project, results, coverage)

        sessions_path = str(storage.get_project_path(sample_project, "sessions.json"))
        data = storage.load_json(sessions_path)
        # sample_project starts with 2 sessions, we added 1
        assert len(data["sessions"]) == 3

    def test_coverage_persists_to_disk(self, sample_project):
        from atenea import storage
        coverage = {"items": {"new": {"ef": 2.0, "interval": 1.0, "reviews": 1, "correct": 0, "status": "testing"}}}
        finish_test(sample_project, [], coverage)

        coverage_path = str(storage.get_project_path(sample_project, "coverage.json"))
        data = storage.load_json(coverage_path)
        assert "new" in data["items"]
        assert "updated" in data


# ============================================================
# build_session_summary
# ============================================================

class TestBuildSessionSummary:

    def _results(self, specs):
        """Build results from list of (correct, targets) tuples."""
        return [
            {"question_id": f"q{i}", "answer": "A", "correct": c, "targets": t}
            for i, (c, t) in enumerate(specs)
        ]

    def _coverage(self, items_dict):
        return {"items": items_dict}

    def test_score_calculation(self):
        results = self._results([(True, ["a"]), (True, ["b"]), (False, ["c"])])
        coverage = self._coverage({
            "a": {"status": "testing", "reviews": 1, "correct": 1, "ef": 2.5, "interval": 1.0},
            "b": {"status": "testing", "reviews": 1, "correct": 1, "ef": 2.5, "interval": 1.0},
            "c": {"status": "testing", "reviews": 1, "correct": 0, "ef": 2.2, "interval": 1.0},
        })
        s = build_session_summary(results, coverage)
        assert s["total"] == 3
        assert s["correct"] == 2
        assert s["score"] == 66.7

    def test_by_target_deduplicates(self):
        """Same target in multiple questions appears once; correct if any was correct."""
        results = self._results([(False, ["shared"]), (True, ["shared"])])
        coverage = self._coverage({
            "shared": {"status": "testing", "reviews": 2, "correct": 1, "ef": 2.3, "interval": 6.0},
        })
        s = build_session_summary(results, coverage)
        terms = [e["term"] for e in s["by_target"]]
        assert terms.count("shared") == 1
        assert s["by_target"][0]["correct"] is True  # True wins

    def test_status_counts(self):
        results = self._results([(True, ["a"]), (True, ["b"]), (False, ["c"])])
        coverage = self._coverage({
            "a": {"status": "known", "reviews": 3, "correct": 3, "ef": 2.6, "interval": 15.0},
            "b": {"status": "testing", "reviews": 2, "correct": 2, "ef": 2.5, "interval": 6.0},
            "c": {"status": "unknown", "reviews": 0, "correct": 0, "ef": 2.5, "interval": 1.0},
        })
        s = build_session_summary(results, coverage)
        assert s["status_counts"]["known"] == 1
        assert s["status_counts"]["testing"] == 1
        assert s["status_counts"]["unknown"] == 1

    def test_trend_first_session(self):
        results = self._results([(True, ["a"])])
        coverage = self._coverage({
            "a": {"status": "testing", "reviews": 1, "correct": 1, "ef": 2.5, "interval": 1.0},
        })
        s = build_session_summary(results, coverage, previous_sessions=None)
        assert s["trend"]["direction"] == "first"
        assert s["trend"]["prev_score"] is None

    def test_trend_up(self):
        results = self._results([(True, ["a"])])
        coverage = self._coverage({
            "a": {"status": "testing", "reviews": 1, "correct": 1, "ef": 2.5, "interval": 1.0},
        })
        prev = [{"score": 50.0}]
        s = build_session_summary(results, coverage, previous_sessions=prev)
        assert s["trend"]["direction"] == "up"
        assert s["trend"]["delta"] == 50.0

    def test_trend_down(self):
        results = self._results([(False, ["a"]), (False, ["b"])])
        coverage = self._coverage({
            "a": {"status": "testing", "reviews": 1, "correct": 0, "ef": 2.2, "interval": 1.0},
            "b": {"status": "testing", "reviews": 1, "correct": 0, "ef": 2.2, "interval": 1.0},
        })
        prev = [{"score": 80.0}]
        s = build_session_summary(results, coverage, previous_sessions=prev)
        assert s["trend"]["direction"] == "down"
        assert s["trend"]["delta"] < 0

    def test_trend_stable(self):
        results = self._results([(True, ["a"]), (False, ["b"])])
        coverage = self._coverage({
            "a": {"status": "testing", "reviews": 1, "correct": 1, "ef": 2.5, "interval": 1.0},
            "b": {"status": "testing", "reviews": 1, "correct": 0, "ef": 2.2, "interval": 1.0},
        })
        prev = [{"score": 50.0}]
        s = build_session_summary(results, coverage, previous_sessions=prev)
        assert s["trend"]["direction"] == "stable"  # 50% vs 50%

    def test_top_struggles_filters_by_ef_and_reviews(self):
        results = self._results([(False, ["hard"]), (True, ["easy"])])
        coverage = self._coverage({
            "hard": {"status": "testing", "reviews": 3, "correct": 1, "ef": 1.5, "interval": 1.0},
            "easy": {"status": "known", "reviews": 5, "correct": 5, "ef": 2.6, "interval": 15.0},
        })
        s = build_session_summary(results, coverage)
        assert len(s["top_struggles"]) == 1
        assert s["top_struggles"][0]["term"] == "hard"
        assert s["top_struggles"][0]["ratio"] == 33  # 1/3

    def test_empty_results(self):
        s = build_session_summary([], {"items": {}})
        assert s["total"] == 0
        assert s["score"] == 0
        assert s["by_target"] == []
        assert s["trend"]["direction"] == "first"


# ============================================================
# get_recent_question_ids
# ============================================================

class TestGetRecentQuestionIds:

    def test_returns_ids_from_last_n_sessions(self, sample_project):
        # sample_project has 2 sessions with results containing question_ids
        ids = get_recent_question_ids(sample_project, n_sessions=2)
        assert isinstance(ids, set)
        # sample_project sessions have question_ids q0-q5
        assert len(ids) > 0

    def test_n_zero_returns_empty(self, sample_project):
        ids = get_recent_question_ids(sample_project, n_sessions=0)
        assert ids == set()

    def test_no_sessions_returns_empty(self, tmp_data_dir):
        # Project without sessions.json
        p = os.path.join(tmp_data_dir, "nosessions")
        os.makedirs(p, exist_ok=True)
        ids = get_recent_question_ids("nosessions", n_sessions=5)
        assert ids == set()

    def test_respects_n_sessions_limit(self, sample_project):
        """With n_sessions=1, only IDs from the last session are returned."""
        ids_1 = get_recent_question_ids(sample_project, n_sessions=1)
        ids_2 = get_recent_question_ids(sample_project, n_sessions=2)
        # 2 sessions should return >= ids than 1 session
        assert len(ids_2) >= len(ids_1)


# ============================================================
# select_questions with recent_ids
# ============================================================

class TestSelectQuestionsWithRecentIds:

    def _questions(self, targets_list):
        return [
            {"id": f"q{i}", "targets": t, "question": f"Q{i}"}
            for i, t in enumerate(targets_list)
        ]

    def test_recent_id_deprioritised(self):
        """A question in recent_ids should be deprioritised but not excluded."""
        qs = self._questions([["unknown_a"], ["unknown_b"]])
        coverage = {"items": {}}  # both unknown
        # q0 was seen recently -> deprioritised to testing bucket
        result = select_questions(qs, coverage, n=1, recent_ids={"q0"})
        # Should prefer q1 (truly unknown) over q0 (demoted to testing)
        assert result[0]["id"] == "q1"

    def test_no_recent_ids_same_as_before(self):
        qs = self._questions([["a"], ["b"], ["c"]])
        coverage = {"items": {}}
        r1 = select_questions(qs, coverage, n=3, recent_ids=None)
        r2 = select_questions(qs, coverage, n=3)
        # Both should return all 3 (order may differ due to shuffle)
        assert len(r1) == 3
        assert len(r2) == 3

    def test_all_recent_still_returns_questions(self):
        """Even if all questions were recently seen, they should still be returned."""
        qs = self._questions([["a"], ["b"]])
        coverage = {"items": {}}
        recent = {"q0", "q1"}
        result = select_questions(qs, coverage, n=2, recent_ids=recent)
        assert len(result) == 2
