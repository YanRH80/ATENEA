"""
tests/test_sm2.py — SM-2 spaced repetition algorithm tests.

Tests update_sm2() from test_service.py against known SM-2 behavior:
- EF adjustment formula
- Interval progression (1 → 6 → EF*interval)
- Status transitions (unknown → testing → known)
- Quality thresholds (passing ≥ 3)
- EF floor (1.3 minimum)
"""

from atenea.services.test_service import update_sm2
from config.defaults import (
    SM2_INITIAL_EF,
    SM2_EF_MINIMUM,
    SM2_INITIAL_INTERVAL_DAYS,
    SM2_SECOND_INTERVAL_DAYS,
    SM2_PASSING_QUALITY,
)


def _fresh():
    """Fresh item — never reviewed."""
    return {"ef": SM2_INITIAL_EF, "interval": SM2_INITIAL_INTERVAL_DAYS, "reviews": 0, "correct": 0}


# ── EF adjustment ────────────────────────────────────────────

class TestEFAdjustment:
    """EF formula: ef + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))"""

    def test_perfect_answer_increases_ef(self):
        result = update_sm2(_fresh(), quality=5)
        assert result["ef"] > SM2_INITIAL_EF

    def test_passing_answer_maintains_ef(self):
        # quality=4 → delta = 0.1 - 1*(0.08 + 0.02) = 0.0
        result = update_sm2(_fresh(), quality=4)
        assert result["ef"] == SM2_INITIAL_EF

    def test_bare_pass_decreases_ef(self):
        # quality=3 → delta = 0.1 - 2*(0.08 + 0.04) = -0.14
        result = update_sm2(_fresh(), quality=3)
        assert result["ef"] < SM2_INITIAL_EF

    def test_fail_decreases_ef_more(self):
        r3 = update_sm2(_fresh(), quality=3)
        r1 = update_sm2(_fresh(), quality=1)
        assert r1["ef"] < r3["ef"]

    def test_ef_never_below_minimum(self):
        item = {"ef": SM2_EF_MINIMUM, "interval": 1.0, "reviews": 5, "correct": 1}
        result = update_sm2(item, quality=0)
        assert result["ef"] >= SM2_EF_MINIMUM

    def test_ef_floor_with_repeated_failures(self):
        item = _fresh()
        for _ in range(20):
            item = update_sm2(item, quality=0)
        assert item["ef"] == SM2_EF_MINIMUM


# ── Interval progression ─────────────────────────────────────

class TestIntervalProgression:

    def test_first_review_sets_initial_interval(self):
        result = update_sm2(_fresh(), quality=4)
        assert result["interval"] == SM2_INITIAL_INTERVAL_DAYS

    def test_second_review_sets_six_days(self):
        item = update_sm2(_fresh(), quality=4)
        result = update_sm2(item, quality=4)
        assert result["interval"] == SM2_SECOND_INTERVAL_DAYS

    def test_third_review_multiplies_by_ef(self):
        item = update_sm2(_fresh(), quality=4)
        item = update_sm2(item, quality=4)
        ef_before = item["ef"]
        result = update_sm2(item, quality=4)
        expected = round(SM2_SECOND_INTERVAL_DAYS * ef_before, 1)
        assert result["interval"] == expected

    def test_fail_resets_interval(self):
        # Build up to interval > 1
        item = update_sm2(_fresh(), quality=5)
        item = update_sm2(item, quality=5)
        assert item["interval"] > SM2_INITIAL_INTERVAL_DAYS
        # Fail resets
        result = update_sm2(item, quality=1)
        assert result["interval"] == SM2_INITIAL_INTERVAL_DAYS

    def test_intervals_grow_monotonically_with_perfect_scores(self):
        item = _fresh()
        intervals = []
        for _ in range(6):
            item = update_sm2(item, quality=5)
            intervals.append(item["interval"])
        # After first two (1.0, 6.0), should grow
        for i in range(2, len(intervals)):
            assert intervals[i] > intervals[i - 1]


# ── Status transitions ───────────────────────────────────────

class TestStatusTransitions:

    def test_first_review_sets_testing(self):
        result = update_sm2(_fresh(), quality=4)
        assert result["status"] == "testing"

    def test_first_review_fail_still_testing(self):
        result = update_sm2(_fresh(), quality=1)
        assert result["status"] == "testing"

    def test_three_reviews_80pct_correct_is_known(self):
        item = _fresh()
        item = update_sm2(item, quality=4)  # 1/1 = 100%
        item = update_sm2(item, quality=4)  # 2/2 = 100%
        item = update_sm2(item, quality=4)  # 3/3 = 100%
        assert item["status"] == "known"

    def test_three_reviews_below_80pct_stays_testing(self):
        item = _fresh()
        item = update_sm2(item, quality=4)  # 1/1
        item = update_sm2(item, quality=1)  # 1/2 = 50%
        item = update_sm2(item, quality=4)  # 2/3 = 66%
        assert item["status"] == "testing"

    def test_known_degrades_after_failures(self):
        # Build to known
        item = _fresh()
        for _ in range(3):
            item = update_sm2(item, quality=5)
        assert item["status"] == "known"
        # Fail twice → ratio drops below 80%
        item = update_sm2(item, quality=0)  # 3/4 = 75%
        assert item["status"] == "testing"


# ── Counter tracking ─────────────────────────────────────────

class TestCounters:

    def test_reviews_increment(self):
        item = _fresh()
        r1 = update_sm2(item, quality=4)
        r2 = update_sm2(r1, quality=4)
        assert r1["reviews"] == 1
        assert r2["reviews"] == 2

    def test_correct_increments_on_pass(self):
        result = update_sm2(_fresh(), quality=4)
        assert result["correct"] == 1

    def test_correct_unchanged_on_fail(self):
        result = update_sm2(_fresh(), quality=1)
        assert result["correct"] == 0

    def test_last_field_is_iso_string(self):
        result = update_sm2(_fresh(), quality=4)
        assert "last" in result
        assert "T" in result["last"]  # ISO 8601 format


# ── Edge cases ───────────────────────────────────────────────

class TestEdgeCases:

    def test_quality_zero(self):
        result = update_sm2(_fresh(), quality=0)
        assert result["reviews"] == 1
        assert result["correct"] == 0
        assert result["ef"] >= SM2_EF_MINIMUM

    def test_quality_five(self):
        result = update_sm2(_fresh(), quality=5)
        assert result["reviews"] == 1
        assert result["correct"] == 1
        assert result["ef"] > SM2_INITIAL_EF

    def test_missing_fields_use_defaults(self):
        result = update_sm2({}, quality=4)
        assert result["reviews"] == 1
        assert result["ef"] == SM2_INITIAL_EF  # quality=4 → delta=0

    def test_passing_quality_boundary(self):
        passing = update_sm2(_fresh(), quality=SM2_PASSING_QUALITY)
        failing = update_sm2(_fresh(), quality=SM2_PASSING_QUALITY - 1)
        assert passing["correct"] == 1
        assert failing["correct"] == 0
