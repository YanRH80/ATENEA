"""Tests for atenea/scoring.py — Learning science mathematics."""

import math
import pytest

from atenea.scoring import (
    update_sm2,
    infer_quality,
    retention,
    needs_review,
    wilson_lower,
    is_mastered,
    mastery_level,
    compute_priority,
    path_score,
    map_score,
    cspoj_component_score,
    should_escalate_bloom,
    compute_consistency,
    bloom_label,
    leitner_next_box,
    leitner_interval,
)
from config import defaults


# ============================================================
# SM-2 SPACED REPETITION
# ============================================================

class TestUpdateSM2:
    def test_first_correct_review(self):
        ef, interval, rep = update_sm2(2.5, 0, 0, quality=4)
        assert ef >= defaults.SM2_EF_MINIMUM
        assert interval == defaults.SM2_INITIAL_INTERVAL_DAYS
        assert rep == 1

    def test_second_correct_review(self):
        ef, interval, rep = update_sm2(2.5, 1.0, 1, quality=4)
        assert interval == defaults.SM2_SECOND_INTERVAL_DAYS
        assert rep == 2

    def test_third_correct_review_uses_ef(self):
        ef, interval, rep = update_sm2(2.5, 6.0, 2, quality=4)
        assert interval == pytest.approx(6.0 * ef, rel=0.01)
        assert rep == 3

    def test_failed_review_resets(self):
        ef, interval, rep = update_sm2(2.5, 30.0, 5, quality=1)
        assert interval == defaults.SM2_INITIAL_INTERVAL_DAYS
        assert rep == 0

    def test_ef_never_below_minimum(self):
        ef, _, _ = update_sm2(1.3, 1.0, 0, quality=0)
        assert ef >= defaults.SM2_EF_MINIMUM

    def test_perfect_quality_increases_ef(self):
        ef, _, _ = update_sm2(2.5, 1.0, 0, quality=5)
        assert ef > 2.5

    def test_low_quality_decreases_ef(self):
        ef, _, _ = update_sm2(2.5, 1.0, 0, quality=3)
        assert ef < 2.5

    def test_passing_boundary(self):
        # quality=3 is exactly passing
        _, interval_pass, rep_pass = update_sm2(2.5, 1.0, 0, quality=3)
        assert rep_pass == 1

        # quality=2 is failing
        _, interval_fail, rep_fail = update_sm2(2.5, 1.0, 0, quality=2)
        assert rep_fail == 0


class TestInferQuality:
    def test_correct_fast(self):
        assert infer_quality(True, False, 3000) == defaults.SM2_QUALITY_FAST_CORRECT

    def test_correct_normal(self):
        assert infer_quality(True, False, 10000) == defaults.SM2_QUALITY_NORMAL_CORRECT

    def test_correct_slow(self):
        assert infer_quality(True, False, 25000) == defaults.SM2_QUALITY_SLOW_CORRECT

    def test_partial(self):
        assert infer_quality(False, True, 5000) == defaults.SM2_QUALITY_CLOSE_INCORRECT

    def test_incorrect(self):
        assert infer_quality(False, False, 5000) == defaults.SM2_QUALITY_INCORRECT

    def test_blank_too_fast(self):
        assert infer_quality(False, False, 500) == defaults.SM2_QUALITY_BLANK


# ============================================================
# EBBINGHAUS FORGETTING CURVE
# ============================================================

class TestRetention:
    def test_just_reviewed(self):
        assert retention(0, 1.0) == 1.0

    def test_negative_time(self):
        assert retention(-1, 1.0) == 1.0

    def test_zero_interval(self):
        assert retention(5, 0) == 0.0

    def test_decays_over_time(self):
        r1 = retention(1, 10.0)
        r2 = retention(5, 10.0)
        r3 = retention(10, 10.0)
        assert 0 < r3 < r2 < r1 < 1.0

    def test_at_interval(self):
        # At t=interval, retention should be approximately RECALL_THRESHOLD
        r = retention(10.0, 10.0)
        assert r == pytest.approx(defaults.RECALL_THRESHOLD, abs=0.01)


class TestNeedsReview:
    def test_fresh_item_no_review(self):
        assert not needs_review(0, 10.0)

    def test_overdue_item_needs_review(self):
        assert needs_review(100, 10.0)

    def test_at_boundary(self):
        # Just past the interval should need review
        assert needs_review(11, 10.0)


# ============================================================
# WILSON SCORE
# ============================================================

class TestWilsonLower:
    def test_zero_total(self):
        assert wilson_lower(0, 0) == 0.0

    def test_all_correct(self):
        score = wilson_lower(10, 10)
        assert 0.7 < score < 1.0

    def test_none_correct(self):
        score = wilson_lower(0, 10)
        assert score == pytest.approx(0.0, abs=0.05)

    def test_conservative_with_few_samples(self):
        # 1/1 should NOT give high confidence
        score_1_of_1 = wilson_lower(1, 1)
        score_10_of_10 = wilson_lower(10, 10)
        assert score_1_of_1 < score_10_of_10

    def test_increases_with_more_data(self):
        s5 = wilson_lower(5, 5)
        s10 = wilson_lower(10, 10)
        s50 = wilson_lower(50, 50)
        assert s5 < s10 < s50

    def test_custom_z(self):
        # Higher Z = more conservative
        low_conf = wilson_lower(8, 10, z=1.0)
        high_conf = wilson_lower(8, 10, z=2.58)
        assert high_conf < low_conf


class TestMastery:
    def test_not_mastered_with_few_reviews(self):
        assert not is_mastered(3, 3)

    def test_mastered_with_many_correct(self):
        # Need ~50 perfect reviews for Wilson lower bound to exceed 0.85
        assert is_mastered(50, 50)

    def test_not_mastered_with_poor_accuracy(self):
        assert not is_mastered(3, 10)

    def test_mastery_level_new(self):
        assert mastery_level(0, 0) == "new"

    def test_mastery_level_learning(self):
        assert mastery_level(1, 5) == "learning"

    def test_mastery_level_mastered(self):
        # Wilson lower bound needs ~50 samples to exceed 0.85
        assert mastery_level(50, 50) == "mastered"


# ============================================================
# PRIORITY
# ============================================================

class TestComputePriority:
    def test_basic_priority(self):
        p = compute_priority(0.5, 0.7, 0.3, 0.8)
        assert 0 < p < 2.0

    def test_unknown_item_higher_priority(self):
        p_unknown = compute_priority(0.0, 0.7, 0.5, 0.3)
        p_known = compute_priority(0.9, 0.7, 0.5, 0.9)
        assert p_unknown > p_known

    def test_new_item_bonus(self):
        p_old = compute_priority(0.5, 0.5, 0.5, 0.5, is_new=False)
        p_new = compute_priority(0.5, 0.5, 0.5, 0.5, is_new=True)
        assert p_new > p_old
        assert p_new - p_old == pytest.approx(defaults.NEW_ITEM_BONUS)

    def test_interleaving_bonus(self):
        # All same context → bonus applied
        p_same = compute_priority(0.5, 0.5, 0.5, 0.5, recent_contexts=["A", "A", "A"])
        p_mixed = compute_priority(0.5, 0.5, 0.5, 0.5, recent_contexts=["A", "B", "C"])
        assert p_same > p_mixed

    def test_no_contexts_no_crash(self):
        p = compute_priority(0.5, 0.5, 0.5, 0.5, recent_contexts=None)
        assert p > 0


# ============================================================
# PATH & MAP SCORING
# ============================================================

class TestPathScore:
    def test_perfect_scores(self):
        s = path_score(1.0, 1.0, 1.0, 1.0)
        assert s == pytest.approx(1.0)

    def test_zero_scores(self):
        s = path_score(0.0, 0.0, 0.0, 0.0)
        assert s == pytest.approx(0.0)

    def test_weights_sum_to_one(self):
        total = (defaults.PATH_WEIGHT_SM2 + defaults.PATH_WEIGHT_RECENCY +
                 defaults.PATH_WEIGHT_CONSISTENCY + defaults.PATH_WEIGHT_RESPONSE_TIME)
        assert total == pytest.approx(1.0)


class TestMapScore:
    def test_empty(self):
        assert map_score([]) == 0.0

    def test_all_perfect(self):
        s = map_score([1.0, 1.0, 1.0])
        assert s == pytest.approx(1.0)

    def test_partial_connectivity(self):
        # Some paths scored, some not
        s_full = map_score([0.8, 0.8, 0.8])
        s_partial = map_score([0.8, 0.8, 0.0])
        assert s_partial < s_full


class TestCSPOJComponentScore:
    def test_all_perfect(self):
        scores = {c: 1.0 for c in defaults.CSPOJ_COMPONENT_WEIGHTS}
        assert cspoj_component_score(scores) == pytest.approx(1.0)

    def test_all_zero(self):
        scores = {c: 0.0 for c in defaults.CSPOJ_COMPONENT_WEIGHTS}
        assert cspoj_component_score(scores) == pytest.approx(0.0)

    def test_weights_sum_to_one(self):
        total = sum(defaults.CSPOJ_COMPONENT_WEIGHTS.values())
        assert total == pytest.approx(1.0)


# ============================================================
# BLOOM'S TAXONOMY & CONSISTENCY
# ============================================================

class TestBloom:
    def test_escalate_at_threshold(self):
        assert should_escalate_bloom(3, 0.85)

    def test_no_escalate_below_threshold(self):
        assert not should_escalate_bloom(3, 0.5)

    def test_no_escalate_at_max(self):
        assert not should_escalate_bloom(6, 1.0)

    def test_bloom_labels(self):
        assert bloom_label(1) == "remember"
        assert bloom_label(6) == "create"


class TestConsistency:
    def test_too_few_samples(self):
        assert compute_consistency([5]) == 0.0

    def test_perfect_consistency(self):
        assert compute_consistency([4, 4, 4, 4, 4]) == 1.0

    def test_max_inconsistency(self):
        # Alternating 0 and 5 should be low consistency
        c = compute_consistency([0, 5, 0, 5, 0])
        assert c < 0.5

    def test_all_zeros(self):
        assert compute_consistency([0, 0, 0]) == 0.0

    def test_moderate_consistency(self):
        c = compute_consistency([3, 4, 3, 4, 3])
        assert 0.7 < c < 1.0


# ============================================================
# LEITNER
# ============================================================

class TestLeitner:
    def test_advance_on_correct(self):
        assert leitner_next_box(1, True) == 2

    def test_reset_on_incorrect(self):
        assert leitner_next_box(5, False) == defaults.LEITNER_FAILURE_BOX

    def test_max_box(self):
        max_box = len(defaults.LEITNER_BOX_INTERVALS) - 1
        assert leitner_next_box(max_box, True) == max_box

    def test_interval_increases(self):
        intervals = [leitner_interval(i) for i in range(len(defaults.LEITNER_BOX_INTERVALS))]
        for i in range(1, len(intervals)):
            assert intervals[i] >= intervals[i - 1]

    def test_interval_out_of_bounds(self):
        last = leitner_interval(100)
        assert last == defaults.LEITNER_BOX_INTERVALS[-1]
