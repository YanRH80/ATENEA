"""
config/models.py — LLM Model Configuration

Granular per-task model selection. Each AI-dependent function reads
its model from MODELS[task_name] and temperature from TEMPERATURES[task_name].

This design supports:
- Using different models per task (cheap for simple, expensive for complex)
- A/B testing models on specific tasks
- Future LoRAs for specialized domains (medicine, law, chemistry, etc.)
- Switching providers by changing one string (litellm format)

Model string format (litellm): "provider/model-name"
Examples:
  "deepseek/deepseek-chat"
  "anthropic/claude-sonnet-4-20250514"
  "openai/gpt-4o"
  "ollama/llama3"
"""

# ============================================================
# DEFAULT MODEL
# ============================================================

# The fallback model for any task not explicitly configured.
# DeepSeek Chat for testing — cheap and capable.
DEFAULT_MODEL = "deepseek/deepseek-chat"


# ============================================================
# PER-TASK MODEL SELECTION
# ============================================================

MODELS = {
    # Step 3: Knowledge extraction
    "extraction_points": DEFAULT_MODEL,   # Simple: filter keywords
    "extraction_paths": DEFAULT_MODEL,    # Complex: build CSPOJ ontology
    "extraction_sets": DEFAULT_MODEL,     # Medium: semantic grouping
    "extraction_maps": DEFAULT_MODEL,     # Complex: meta-paths

    # Step 4: Question generation
    "question_gen_tf": DEFAULT_MODEL,     # Generate false statements
    "question_gen_mc": DEFAULT_MODEL,     # Generate distractors

    # Step 5: Answer evaluation
    "evaluation": DEFAULT_MODEL,          # Judge free-text answers

    # Advisor module
    "advisor": DEFAULT_MODEL,             # Meta-learning suggestions
    "domain_detection": DEFAULT_MODEL,    # Detect content domain
    "prompt_evolution": DEFAULT_MODEL,    # Improve prompts

    # Fallback for language detection (if langdetect fails)
    "language_detection": DEFAULT_MODEL,
}


# ============================================================
# PER-TASK TEMPERATURE
# ============================================================

TEMPERATURES = {
    # Extraction: low temperature for precision and consistency
    "extraction_points": 0.3,
    "extraction_paths": 0.3,
    "extraction_sets": 0.3,
    "extraction_maps": 0.3,

    # Question generation: higher temperature for creative distractors
    "question_gen_tf": 0.7,
    "question_gen_mc": 0.7,

    # Evaluation: very low for consistent grading
    "evaluation": 0.1,

    # Advisor: moderate for balanced suggestions
    "advisor": 0.5,
    "domain_detection": 0.2,
    "prompt_evolution": 0.5,

    # Language detection
    "language_detection": 0.0,
}


# ============================================================
# PER-DOMAIN MODEL OVERRIDES (Future: LoRAs)
# ============================================================

# When the advisor detects a domain (e.g., "medicina"), it can
# suggest switching specific tasks to a specialized model.
# Uncomment and edit as specialized models become available.
#
# Format: domain -> { task_name -> model_string }
DOMAIN_MODEL_OVERRIDES = {
    # "medicina": {
    #     "extraction_paths": "deepseek/deepseek-chat-medical-lora",
    #     "evaluation": "deepseek/deepseek-chat-medical-lora",
    # },
    # "legal": {
    #     "extraction_paths": "deepseek/deepseek-chat-legal-lora",
    # },
    # "matematicas": {
    #     "extraction_paths": "deepseek/deepseek-chat-math-lora",
    # },
    # "quimica": {
    #     "extraction_paths": "deepseek/deepseek-chat-chemistry-lora",
    # },
}


# ============================================================
# GENERAL LLM PARAMETERS
# ============================================================

MAX_TOKENS = 4096
MAX_RETRIES = 2     # Retry on failure (JSON parse error, API timeout)
REQUEST_TIMEOUT = 60  # Seconds before timeout


# ============================================================
# HELPER FUNCTION
# ============================================================

def get_model(task, domain=None):
    """Resolve the model for a task, with optional domain override.

    Args:
        task: Key in MODELS dict (e.g., "extraction_paths").
        domain: Optional domain string (e.g., "medicina").

    Returns:
        Model string in litellm format.
    """
    if domain and domain in DOMAIN_MODEL_OVERRIDES:
        overrides = DOMAIN_MODEL_OVERRIDES[domain]
        if task in overrides:
            return overrides[task]
    return MODELS.get(task, DEFAULT_MODEL)


def get_temperature(task):
    """Resolve the temperature for a task.

    Args:
        task: Key in TEMPERATURES dict.

    Returns:
        Temperature float.
    """
    return TEMPERATURES.get(task, 0.3)
