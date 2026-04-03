"""
config/defaults.py — Atenea Global Configuration

Every constant is documented with the scientific reference it derives from.
Modifying these values tunes question generation, answer scoring, and
priority updates. All variables are plain module-level values — no classes.

Edit this file directly to fine-tune the system. Every AI-dependent function
reads from here at call time, so changes take effect immediately.
"""

import math

# ============================================================
# PATHS & STRUCTURE
# ============================================================

# Default root directory for project data (each project is a subdirectory).
DEFAULT_DATA_DIR = "./data"

# 7±2 Rule — Miller, G.A. (1956). "The Magical Number Seven, Plus or
# Minus Two: Some Limits on Our Capacity for Processing Information."
# Psychological Review, 63(2), 81-97.
#
# Human working memory can hold ~7 items simultaneously. CSPOJ paths
# should reference 5-9 points, and maps should contain 5-9 paths,
# to match this cognitive limit.
MIN_ELEMENTS = 5   # 7 - 2
MAX_ELEMENTS = 9   # 7 + 2


# ============================================================
# SPACED REPETITION — SM-2 Algorithm
#
# Wozniak, P.A. (1990). "Optimization of repetition spacing in the
# practice of learning." University of Technology in Poznań.
# Used in SuperMemo 2, later adapted by Anki (Damien Elmes, 2006).
#
# Core idea: after each review, the "easiness factor" (EF) adjusts
# how quickly the interval grows. Easy items get longer intervals;
# hard items get shorter ones.
# ============================================================

# Initial easiness factor for new items.
# 2.5 means "medium difficulty" — intervals grow by 2.5x after each
# successful recall. Range: [EF_MINIMUM, ∞). In practice, stays 1.3-3.5.
SM2_INITIAL_EF = 2.5

# Minimum easiness factor. Prevents items from becoming "impossible."
# Even the hardest item still gets intervals that grow (slowly).
SM2_EF_MINIMUM = 1.3

# First interval after initial learning: 1 day.
# Short enough to consolidate the initial memory trace.
SM2_INITIAL_INTERVAL_DAYS = 1.0

# Second interval: 6 days.
# After the first successful 1-day recall, the memory has been
# consolidated enough to survive a longer gap.
# Ref: Roediger, H.L. & Karpicke, J.D. (2006). "Test-Enhanced
# Learning." Psychological Science, 17(3), 249-255.
SM2_SECOND_INTERVAL_DAYS = 6.0

# Quality threshold: scores 0-2 = fail (reset interval), 3-5 = pass.
SM2_PASSING_QUALITY = 3

# --- Quality auto-inference ---
# When the system grades automatically (not self-report), it maps
# correctness + response time to the 0-5 quality scale:
SM2_QUALITY_FAST_CORRECT = 5      # Correct + fast → confident recall
SM2_QUALITY_NORMAL_CORRECT = 4    # Correct + normal time
SM2_QUALITY_SLOW_CORRECT = 3      # Correct but struggled
SM2_QUALITY_CLOSE_INCORRECT = 2   # Wrong but close (partial credit)
SM2_QUALITY_INCORRECT = 1         # Wrong
SM2_QUALITY_BLANK = 0             # No answer / timeout


# ============================================================
# EBBINGHAUS FORGETTING CURVE
#
# Ebbinghaus, H. (1885). "Über das Gedächtnis." Leipzig: Duncker.
#
# Formula: R(t) = e^(-t / S)
#   R = retention probability [0, 1]
#   t = time since last review (days)
#   S = memory stability (days) — how slowly the memory decays
#
# After a successful review at interval I, we expect the student
# to remember with probability ~RECALL_THRESHOLD at time I.
# Therefore: S = -I / ln(RECALL_THRESHOLD)
# ============================================================

# Target retention at the moment of scheduled review.
# 0.85 = 85% chance of recall. Standard in Anki and SuperMemo.
# Ref: Settles, B. & Meeder, B. (2016). "A Trainable Spaced
# Repetition Model for Language Learning." ACL.
RECALL_THRESHOLD = 0.85

# Derived: stability scalar. S = interval * STABILITY_SCALAR.
# With RECALL_THRESHOLD=0.85: -1/ln(0.85) ≈ 6.15.
STABILITY_SCALAR = -1.0 / math.log(RECALL_THRESHOLD)  # ~6.15

# Below this retention, the item is essentially forgotten.
# Re-learning, not reviewing.
CRITICAL_RETENTION = 0.50


# ============================================================
# LEITNER SYSTEM — Box-Based Spaced Repetition
#
# Leitner, S. (1972). "So lernt man lernen." Freiburg: Herder.
#
# Simpler than SM-2. Each item lives in a "box." Correct → promote
# to next box (longer interval). Incorrect → demote to box 1.
# Used for visualization and gamification in the UI.
# ============================================================

LEITNER_BOX_INTERVALS = [0.0, 1.0, 3.0, 7.0, 14.0, 30.0, 60.0, 120.0]
LEITNER_FAILURE_BOX = 1


# ============================================================
# KNOWLEDGE SCORING — Points, Paths, Maps
# ============================================================

# --- Point mastery (individual concept/keyword) ---
# Uses the Wilson score lower bound to avoid false positives.
# A student who got 1/1 correct is NOT "100% mastered" — the Wilson
# lower bound for 1/1 at 95% CI is only ~0.21.
# Ref: Wilson, E.B. (1927). "Probable Inference." JASA, 22(158).

MASTERY_THRESHOLD = 0.85   # Wilson lower bound >= this = mastered
FAMILIAR_THRESHOLD = 0.50  # Between familiar and mastery
# Below FAMILIAR_THRESHOLD = unknown

# Minimum reviews before mastery can be declared.
# Need N >= 5 for Wilson score to have a meaningful lower bound.
MIN_REVIEWS_FOR_MASTERY = 5
MIN_REVIEWS_FOR_FAMILIAR = 2

# --- Path score (CSPOJ relationship) ---
# Weighted composite of four sub-scores:
#   1. SM-2 derived mastery signal (core learning metric)
#   2. Ebbinghaus retention right now (time-based decay)
#   3. Consistency (low variance = reliable knowledge, not guessing)
#   4. Response time (fluency/automaticity)
# Ref (automaticity): Logan, G.D. (1988). "Toward an Instance Theory
# of Automatization." Psychological Review, 95(4), 492-527.

PATH_WEIGHT_SM2 = 0.50
PATH_WEIGHT_RECENCY = 0.20
PATH_WEIGHT_CONSISTENCY = 0.20
PATH_WEIGHT_RESPONSE_TIME = 0.10

# Response time boundaries (milliseconds)
EXPECTED_RESPONSE_TIME_MS = 10000   # 10s = normal cued recall
MIN_PLAUSIBLE_RESPONSE_TIME_MS = 1500  # <1.5s = probable guess
RESPONSE_TIME_FAST_MS = 5000        # <5s = confident
RESPONSE_TIME_SLOW_MS = 20000       # >20s = struggled
ANSWER_TIMEOUT_MS = 60000           # 60s timeout

# Number of recent quality scores for consistency calculation.
CONSISTENCY_WINDOW = 5

# --- Map score (topic/subgraph) ---
# True understanding requires connected knowledge, not isolated facts.
# Ref: Schema Theory — Piaget (1936); diSessa (1993) "Knowledge in Pieces."
#
# Connectivity bonus: map_score = mean(path_scores) * connectivity^EXPONENT
# EXPONENT=0.5 (sqrt): generous — 50% edges known → 71% bonus.
CONNECTIVITY_EXPONENT = 0.5


# ============================================================
# PRIORITY — What to Study Next
#
# Combines four factors to rank items for the next test session.
# Weights must sum to 1.0.
#
# Ref (ZPD): Vygotsky, L.S. (1978). "Mind in Society." Harvard UP.
# Ref (Desirable Difficulties): Bjork, R.A. (1994). "Memory and
#   Metamemory Considerations in the Training of Human Beings."
# Ref (Testing Effect): Roediger & Karpicke (2006).
# ============================================================

W_URGENCY = 0.30       # What is unknown (low accuracy)
W_LEARNABILITY = 0.25  # Connects to known concepts (Vygotsky ZPD)
W_IMPORTANCE = 0.20    # High centrality in knowledge graph
W_FORGOTTEN = 0.25     # About to be forgotten (Ebbinghaus)

# Interleaving: switching topics improves long-term retention.
# Ref: Bjork, R.A. & Bjork, E.L. (2011). "Making things hard on
# yourself, but in a good way."
INTERLEAVE_BONUS = 1.15       # 15% boost for switching context
INTERLEAVE_LOOKBACK = 3       # Check last N items for same context

# Never-seen items get a small bonus to ensure exposure.
# Ref: Curiosity-driven learning — Oudeyer, Kaplan & Hafner (2007).
NEW_ITEM_BONUS = 0.10

# Max proportion of new items per session (prevent overload).
# Ref: Anki default ~20 new / 100 review per day.
MAX_NEW_ITEM_RATIO = 0.25

# Items below this priority are considered "mastered and stable."
MIN_PRIORITY_FOR_REVIEW = 0.05


# ============================================================
# CONFIDENCE — Wilson Score Interval
#
# Wilson, E.B. (1927). "Probable Inference, the Law of Succession,
# and Statistical Inference." JASA, 22(158), 209-212.
#
# Distinguishes "actually knows" from "got lucky." The Wilson score
# lower bound gives a conservative estimate of true ability.
# ============================================================

# Z-value for confidence interval. 1.96 = 95% confidence.
CONFIDENCE_Z = 1.96

# If std deviation of quality scores exceeds this, possible guessing.
# Max possible stddev with q in [0,5] is ~2.5.
LUCKY_GUESS_STDDEV_THRESHOLD = 1.5

# Minimum data points before applying consistency checks.
MIN_SAMPLES_FOR_CONSISTENCY = 3

# Penalty to quality score when response time < MIN_PLAUSIBLE.
FAST_GUESS_QUALITY_PENALTY = 1


# ============================================================
# BLOOM'S TAXONOMY — Question Difficulty Levels
#
# Anderson, L.W. & Krathwohl, D.R. (2001). "A Taxonomy for
# Learning, Teaching, and Assessing." Longman.
#
# Categorizes CSPOJ questions by cognitive demand. The system
# escalates through levels as the student demonstrates mastery.
# ============================================================

BLOOM_LEVELS = {
    1: "remember",     # Recall facts: "What is X?"
    2: "understand",   # Explain: "Why does X relate to Y?"
    3: "apply",        # Use in new context: "Given Z, what happens to X?"
    4: "analyze",      # Break apart: "Compare X and Y in context C"
    5: "evaluate",     # Judge: "Is the justification J valid for P(S,O)?"
    6: "create",       # Synthesize: "Propose alternative J for P(S,O)"
}

# Minimum mastery at current Bloom level before advancing.
# Ref: Vygotsky's ZPD — only advance when foundation is solid.
BLOOM_ADVANCE_THRESHOLD = 0.80

# Probability of escalating to higher Bloom level after mastery.
BLOOM_ESCALATION_PROBABILITY = 0.60


# ============================================================
# CSPOJ COMPONENT DIFFICULTY & WEIGHTS
#
# Hiding different CSPOJ components creates questions of different
# difficulty. Hiding the Object (cued recall) is easiest; hiding
# the Context (requires understanding the full domain) is hardest.
# ============================================================

CSPOJ_COMPONENT_DIFFICULTY = {
    "object": 1,          # "Mitochondria produces ___"
    "subject": 2,         # "___ produces ATP"
    "predicate": 3,       # "Mitochondria ___ ATP"
    "justification": 4,   # "Mitochondria produces ATP because ___"
    "context": 5,         # "In the field of ___, mitochondria produces ATP"
}

# Weight of each component in overall path mastery.
# Justification carries more weight: understanding "why" indicates
# deeper learning (Bloom levels 4-6).
CSPOJ_COMPONENT_WEIGHTS = {
    "object": 0.15,
    "subject": 0.15,
    "predicate": 0.20,
    "justification": 0.30,
    "context": 0.20,
}


# ============================================================
# SESSION PARAMETERS
# ============================================================

# Default questions per test session. ~10-15 min at ~30s per question.
# Ref: Miller (1956) working memory + Dempster (1988) spacing effect.
DEFAULT_QUESTIONS_PER_TEST = 25
MIN_SESSION_SIZE = 5
MAX_SESSION_SIZE = 50

# Re-ask a new item after this many intervening items (within session).
# Ref: Karpicke, J.D. & Roediger, H.L. (2008). "The Critical
# Importance of Retrieval for Learning." Science, 319, 966-968.
INTRA_SESSION_SPACING = 4

# Context switching probability within a session.
CONTEXT_SWITCH_PROBABILITY = 0.20


# ============================================================
# SEMANTIC MATCHING (free-text evaluation)
# ============================================================

# Thresholds for AI-evaluated free-text answers.
EXACT_MATCH_THRESHOLD = 0.90   # >= this = quality 4-5
PARTIAL_MATCH_THRESHOLD = 0.60 # >= this = quality 2-3


# ============================================================
# GRAPH CENTRALITY
#
# Freeman, L.C. (1978). "Centrality in Social Networks."
# Social Networks, 1(3), 215-239.
#
# Used to calculate importance_score for priority ranking.
# ============================================================

CENTRALITY_ALGORITHM = "degree"  # "degree", "betweenness", or "pagerank"
PAGERANK_DAMPING = 0.85          # Standard (Brin & Page, 1998)
MIN_CENTRALITY = 0.05            # Baseline importance for isolated nodes
