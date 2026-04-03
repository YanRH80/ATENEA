"""
atenea/scoring.py — Learning Science Mathematics

All scoring, spaced repetition, and priority algorithms in one module.
Used by test_engine.py (during tests) and analyze.py (for analytics).

== Algorithms implemented ==

1. SM-2 Spaced Repetition (Wozniak, 1990)
   - update_sm2(): Updates EF, interval, and repetition count after a review
   - infer_quality(): Maps response correctness + time to SM-2 quality (0-5)

2. Ebbinghaus Forgetting Curve (1885)
   - retention(): Probability of recall at time t
   - needs_review(): Whether an item should be reviewed now

3. Wilson Score Confidence (1927)
   - wilson_lower(): Lower bound of confidence interval for mastery
   - is_mastered(): Whether an item is considered mastered

4. Priority Calculation (Vygotsky ZPD + Bjork Desirable Difficulties)
   - compute_priority(): What to study next

5. Path/Map Scoring
   - path_score(): Composite score for a CSPOJ path
   - map_score(): Score for a map based on its paths

No classes. Pure functions. All parameters come from config/defaults.py.
"""

import math
from datetime import datetime, timezone

from config import defaults


# ============================================================
# SM-2 SPACED REPETITION (Wozniak, 1990)
# ============================================================

def update_sm2(ef, interval, repetition, quality):
    """Update SM-2 parameters after a review.

    The SM-2 algorithm adjusts how soon you'll see an item again
    based on how well you recalled it.

    Args:
        ef: Current Easiness Factor (starts at 2.5).
        interval: Current interval in days.
        repetition: Number of consecutive correct recalls.
        quality: Review quality 0-5 (0=blackout, 5=perfect).

    Returns:
        tuple (new_ef, new_interval, new_repetition)
    """
    # Update easiness factor
    new_ef = ef + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    new_ef = max(new_ef, defaults.SM2_EF_MINIMUM)

    if quality < defaults.SM2_PASSING_QUALITY:
        # Failed: reset to beginning
        new_interval = defaults.SM2_INITIAL_INTERVAL_DAYS
        new_repetition = 0
    else:
        # Passed: advance
        if repetition == 0:
            new_interval = defaults.SM2_INITIAL_INTERVAL_DAYS
        elif repetition == 1:
            new_interval = defaults.SM2_SECOND_INTERVAL_DAYS
        else:
            new_interval = interval * new_ef
        new_repetition = repetition + 1

    return new_ef, new_interval, new_repetition


def infer_quality(is_correct, is_partial, response_time_ms):
    """Infer SM-2 quality (0-5) from response correctness and timing.

    Maps the combination of correctness and response speed to a
    quality score that SM-2 uses to adjust the schedule.

    Args:
        is_correct: True if the answer was fully correct.
        is_partial: True if the answer was partially correct (0.5).
        response_time_ms: Time taken to answer in milliseconds.

    Returns:
        int — quality score 0-5.
    """
    if not is_correct and not is_partial:
        if response_time_ms < defaults.MIN_PLAUSIBLE_RESPONSE_TIME_MS:
            return defaults.SM2_QUALITY_BLANK  # 0: too fast = didn't try
        return defaults.SM2_QUALITY_INCORRECT  # 1

    if is_partial:
        return defaults.SM2_QUALITY_CLOSE_INCORRECT  # 2

    # Correct answer — quality depends on speed
    if response_time_ms < defaults.RESPONSE_TIME_FAST_MS:
        return defaults.SM2_QUALITY_FAST_CORRECT  # 5: fast and correct
    elif response_time_ms < defaults.RESPONSE_TIME_SLOW_MS:
        return defaults.SM2_QUALITY_NORMAL_CORRECT  # 4: normal speed
    else:
        return defaults.SM2_QUALITY_SLOW_CORRECT  # 3: slow but correct


# ============================================================
# EBBINGHAUS FORGETTING CURVE (1885)
# R(t) = e^(-t / S)
# S = interval * STABILITY_SCALAR
# ============================================================

def retention(days_since_review, interval):
    """Calculate probability of recall using the forgetting curve.

    R(t) = e^(-t/S) where S = interval * STABILITY_SCALAR.
    A freshly reviewed item has R=1.0. As time passes, R decays
    toward 0. At t=interval, R ≈ RECALL_THRESHOLD (0.85).

    Args:
        days_since_review: Days since the last review.
        interval: Current SM-2 interval in days.

    Returns:
        float — retention probability [0, 1].
    """
    if days_since_review <= 0:
        return 1.0
    if interval <= 0:
        return 0.0

    stability = interval * defaults.STABILITY_SCALAR
    return math.exp(-days_since_review / stability)


def needs_review(days_since_review, interval):
    """Check if an item needs review based on the forgetting curve.

    An item needs review when its retention drops below
    RECALL_THRESHOLD (default 0.85).

    Args:
        days_since_review: Days since last review.
        interval: Current SM-2 interval in days.

    Returns:
        bool — True if the item should be reviewed.
    """
    return retention(days_since_review, interval) < defaults.RECALL_THRESHOLD


def days_since(iso_timestamp):
    """Calculate days elapsed since an ISO timestamp.

    Args:
        iso_timestamp: ISO 8601 datetime string.

    Returns:
        float — days elapsed. 0 if timestamp is invalid.
    """
    if not iso_timestamp:
        return 0.0
    try:
        then = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max((now - then).total_seconds() / 86400, 0.0)
    except (ValueError, TypeError):
        return 0.0


# ============================================================
# WILSON SCORE CONFIDENCE (1927)
# ============================================================

def wilson_lower(correct, total, z=None):
    """Calculate the Wilson score lower bound.

    Avoids the "1 of 1 = 100%" false positive. With few samples,
    the lower bound is conservative. With many samples, it
    converges to the true proportion.

    Args:
        correct: Number of correct responses.
        total: Total number of responses.
        z: Z-score for confidence interval (default from config: 1.96 = 95%).

    Returns:
        float — lower bound of the confidence interval [0, 1].
    """
    if total == 0:
        return 0.0

    z = z or defaults.CONFIDENCE_Z
    p = correct / total
    n = total

    denominator = 1 + z * z / n
    centre = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)

    return max((centre - spread) / denominator, 0.0)


def is_mastered(correct, total):
    """Check if an item is considered mastered.

    Mastery requires:
    1. Wilson lower bound >= MASTERY_THRESHOLD (0.85)
    2. At least MIN_REVIEWS_FOR_MASTERY (5) reviews

    Args:
        correct: Number of correct responses.
        total: Total number of responses.

    Returns:
        bool — True if mastered.
    """
    if total < defaults.MIN_REVIEWS_FOR_MASTERY:
        return False
    return wilson_lower(correct, total) >= defaults.MASTERY_THRESHOLD


def mastery_level(correct, total):
    """Classify mastery into a human-readable level.

    Args:
        correct: Number of correct responses.
        total: Total number of responses.

    Returns:
        str — "mastered", "familiar", "learning", or "new".
    """
    if total == 0:
        return "new"

    score = wilson_lower(correct, total)

    if total >= defaults.MIN_REVIEWS_FOR_MASTERY and score >= defaults.MASTERY_THRESHOLD:
        return "mastered"
    elif score >= defaults.FAMILIAR_THRESHOLD:
        return "familiar"
    else:
        return "learning"


# ============================================================
# PRIORITY — What to Study Next
# Vygotsky (1978) ZPD + Bjork (1994) Desirable Difficulties
# ============================================================

def compute_priority(path_score_val, connected_mastery, centrality,
                     retention_val, recent_contexts=None, is_new=False):
    """Calculate priority score for a CSPOJ path.

    Higher priority = should be studied sooner. Combines 4 factors:

    1. Urgency (W=0.30): How unknown the path is (1 - path_score)
    2. Learnability (W=0.25): Mean mastery of connected concepts (ZPD)
    3. Importance (W=0.20): Centrality in the knowledge graph
    4. Forgotten (W=0.25): How close to being forgotten (1 - retention)

    Bonuses:
    - Interleaving: 15% boost if the context differs from recent questions
    - New item: 10% boost for never-seen items (curiosity-driven)

    Args:
        path_score_val: Current composite score of the path [0, 1].
        connected_mastery: Mean mastery of connected points [0, 1].
        centrality: Graph centrality of the path's concepts [0, 1].
        retention_val: Current retention probability [0, 1].
        recent_contexts: List of recent question contexts (for interleaving).
        is_new: Whether this path has never been tested.

    Returns:
        float — priority score (higher = study sooner).
    """
    urgency = 1.0 - path_score_val
    learnability = connected_mastery  # Higher = more ready to learn (ZPD)
    importance = centrality
    forgotten = 1.0 - retention_val

    priority = (
        defaults.W_URGENCY * urgency
        + defaults.W_LEARNABILITY * learnability
        + defaults.W_IMPORTANCE * importance
        + defaults.W_FORGOTTEN * forgotten
    )

    # Interleaving bonus (Bjork, 2011)
    # Boost if the context differs from the last N questions
    if recent_contexts:
        lookback = recent_contexts[-defaults.INTERLEAVE_LOOKBACK:]
        # If context is not in recent lookback, apply bonus for context switching
        # (caller must pass current path's context via recent_contexts comparison)
        # We check if all recent contexts are the same — if so, switching is valuable
        if lookback and len(set(lookback)) == 1:
            priority *= defaults.INTERLEAVE_BONUS

    # New item bonus (Oudeyer, 2007: curiosity-driven exploration)
    if is_new:
        priority += defaults.NEW_ITEM_BONUS

    return priority


# ============================================================
# PATH & MAP SCORING
# ============================================================

def path_score(sm2_quality_avg, retention_val, consistency, response_time_ratio):
    """Compute composite score for a CSPOJ path.

    Combines 4 signals:
    - SM-2 quality average (50%): How well the student recalls
    - Retention/recency (20%): Current forgetting curve position
    - Consistency (20%): Variance in quality scores (IRT)
    - Response time (10%): Fluency / automaticity (Logan, 1988)

    Args:
        sm2_quality_avg: Average SM-2 quality normalized to [0, 1].
        retention_val: Current retention from forgetting curve [0, 1].
        consistency: 1 - normalized_stddev of quality scores [0, 1].
        response_time_ratio: expected_time / actual_time, capped at [0, 1].

    Returns:
        float — composite score [0, 1].
    """
    return (
        defaults.PATH_WEIGHT_SM2 * sm2_quality_avg
        + defaults.PATH_WEIGHT_RECENCY * retention_val
        + defaults.PATH_WEIGHT_CONSISTENCY * consistency
        + defaults.PATH_WEIGHT_RESPONSE_TIME * response_time_ratio
    )


def map_score(path_scores):
    """Compute score for a map based on its constituent paths.

    Uses a connectivity bonus: sqrt gives generous credit for
    partial mastery of paths within the map.

    Args:
        path_scores: List of float scores for each path in the map.

    Returns:
        float — map score [0, 1].
    """
    if not path_scores:
        return 0.0

    mean_score = sum(path_scores) / len(path_scores)
    # Connectivity bonus: reward having more paths scored
    connectivity = len([s for s in path_scores if s > 0]) / len(path_scores)

    return mean_score * (connectivity ** defaults.CONNECTIVITY_EXPONENT)


# ============================================================
# CSPOJ COMPONENT SCORING
# ============================================================

def cspoj_component_score(component_scores):
    """Compute weighted score across CSPOJ components.

    Each component (C, S, P, O, J) has a different weight reflecting
    its difficulty and importance.

    Args:
        component_scores: Dict mapping component name to score [0, 1].
            Keys: "context", "subject", "predicate", "object", "justification"

    Returns:
        float — weighted composite score [0, 1].
    """
    total = 0.0
    for component, weight in defaults.CSPOJ_COMPONENT_WEIGHTS.items():
        score = component_scores.get(component, 0.0)
        total += weight * score
    return total


# ============================================================
# BLOOM'S TAXONOMY
# ============================================================

def should_escalate_bloom(current_level, component_mastery):
    """Decide whether to increase the Bloom's taxonomy level.

    Escalation happens when the student demonstrates mastery at the
    current level, with a probabilistic element to avoid predictability.

    Args:
        current_level: Current Bloom's level (1-6).
        component_mastery: Mastery score for the component [0, 1].

    Returns:
        bool — True if the next question should be at a higher level.
    """
    if current_level >= 6:
        return False
    return component_mastery >= defaults.BLOOM_ADVANCE_THRESHOLD


def compute_consistency(qualities):
    """Compute consistency score from a list of SM-2 quality scores.

    Consistency = 1 - normalized_stddev. A student who scores
    consistently (even if not perfectly) gets a higher consistency
    than one who oscillates between 0 and 5.

    Args:
        qualities: List of SM-2 quality scores (0-5).

    Returns:
        float — consistency score [0, 1]. 1.0 = perfectly consistent.
    """
    if len(qualities) < defaults.MIN_SAMPLES_FOR_CONSISTENCY:
        return 0.0

    mean = sum(qualities) / len(qualities)
    if mean == 0:
        return 0.0

    variance = sum((q - mean) ** 2 for q in qualities) / len(qualities)
    stddev = math.sqrt(variance)
    # Normalize: max possible stddev for 0-5 range is 2.5
    normalized_stddev = stddev / 2.5
    return max(1.0 - normalized_stddev, 0.0)


def bloom_label(level):
    """Get the human-readable Bloom's taxonomy label.

    Args:
        level: Bloom's level (1-6).

    Returns:
        str — label like "remember", "understand", etc.
    """
    return defaults.BLOOM_LEVELS.get(level, "remember")


# ============================================================
# LEITNER BOX (Visual alternative to SM-2)
# ============================================================

def leitner_next_box(current_box, is_correct):
    """Calculate the next Leitner box after a review.

    Correct → advance one box (longer interval).
    Incorrect → back to box 1 (shortest interval).

    Args:
        current_box: Current box number (0-7).
        is_correct: Whether the answer was correct.

    Returns:
        int — new box number.
    """
    if is_correct:
        return min(current_box + 1, len(defaults.LEITNER_BOX_INTERVALS) - 1)
    return defaults.LEITNER_FAILURE_BOX


def leitner_interval(box):
    """Get the review interval for a Leitner box.

    Args:
        box: Box number (0-7).

    Returns:
        int — interval in days.
    """
    if 0 <= box < len(defaults.LEITNER_BOX_INTERVALS):
        return defaults.LEITNER_BOX_INTERVALS[box]
    return defaults.LEITNER_BOX_INTERVALS[-1]
