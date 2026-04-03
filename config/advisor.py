"""
config/advisor.py — AI Advisor Configuration

The advisor module's own config. These values can be proposed for
modification by the advisor itself (with user approval).
"""

# Model used for advisor tasks (can differ from extraction model).
ADVISOR_MODEL = "deepseek/deepseek-chat"
ADVISOR_TEMPERATURE = 0.5

# After how many test sessions should the advisor proactively suggest changes?
AUTO_SUGGEST_AFTER_N_SESSIONS = 3

# Minimum data points before the advisor can propose prompt evolution.
# Prevents premature optimization on insufficient data.
PROMPT_EVOLUTION_MIN_DATA_POINTS = 10

# Minimum confidence for domain detection to trigger prompt specialization.
DOMAIN_DETECTION_CONFIDENCE_THRESHOLD = 0.80

# How literally to interpret user feedback (0=very loose, 1=very strict).
FEEDBACK_INTERPRETATION_STRICTNESS = 0.7

# Maximum number of suggestions per advisor session.
MAX_SUGGESTIONS_PER_SESSION = 5

# How many prompt versions to keep for rollback.
PROMPT_VERSION_RETENTION = 10
