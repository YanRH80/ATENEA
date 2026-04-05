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
