"""
config/models.py — LLM Model Configuration

Per-task model selection. Model string format (litellm): "provider/model-name"
"""

DEFAULT_MODEL = "deepseek/deepseek-chat"

MODELS = {
    "extraction_points": DEFAULT_MODEL,
    "extraction_paths": DEFAULT_MODEL,
    "extraction_sets": DEFAULT_MODEL,
    "extraction_maps": DEFAULT_MODEL,
    "question_gen_tf": DEFAULT_MODEL,
    "question_gen_mc": DEFAULT_MODEL,
    "evaluation": DEFAULT_MODEL,
}

TEMPERATURES = {
    "extraction_points": 0.3,
    "extraction_paths": 0.3,
    "extraction_sets": 0.3,
    "extraction_maps": 0.3,
    "question_gen_tf": 0.7,
    "question_gen_mc": 0.7,
    "evaluation": 0.1,
}

MAX_TOKENS = 4096
MAX_RETRIES = 2
REQUEST_TIMEOUT = 60


def get_model(task, domain=None):
    """Resolve the model for a task."""
    return MODELS.get(task, DEFAULT_MODEL)


def get_temperature(task):
    """Resolve the temperature for a task."""
    return TEMPERATURES.get(task, 0.3)
