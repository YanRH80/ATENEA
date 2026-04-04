"""
config/models.py — LLM Model Configuration

Two tiers:
  - BIG_MODEL: heavy reasoning (knowledge extraction, question generation)
  - SMALL_MODEL: fast helper (advisor, chunking, metadata enrichment)

Model string format (litellm): "provider/model-name"
"""

# ============================================================
# MODEL TIERS
# ============================================================

BIG_MODEL = "deepseek/deepseek-reasoner"      # DeepSeek-R1: CoT reasoning
SMALL_MODEL = "deepseek/deepseek-chat"         # DeepSeek-V3: fast, cheap

# ============================================================
# TASK → MODEL MAPPING
# ============================================================

MODELS = {
    # Heavy tasks → big model
    "extraction": BIG_MODEL,
    "question_gen": BIG_MODEL,
    "evaluation": BIG_MODEL,
    # Light tasks → small model
    "advisor": SMALL_MODEL,
    "chunk_split": SMALL_MODEL,
    "metadata": SMALL_MODEL,
    "summary": SMALL_MODEL,
}

# ============================================================
# TASK → TEMPERATURE
# ============================================================

TEMPERATURES = {
    "extraction": 0.3,
    "question_gen": 0.7,
    "evaluation": 0.1,
    "advisor": 0.6,
    "chunk_split": 0.1,
    "metadata": 0.1,
    "summary": 0.4,
}

# ============================================================
# LIMITS
# ============================================================

MAX_TOKENS = 8192
MAX_RETRIES = 2
REQUEST_TIMEOUT = 300  # 5 min — large extraction prompts need time


def get_model(task, override=None):
    """Resolve the model for a task. Override takes precedence."""
    if override:
        return override
    return MODELS.get(task, SMALL_MODEL)


def get_temperature(task):
    """Resolve the temperature for a task."""
    return TEMPERATURES.get(task, 0.3)
