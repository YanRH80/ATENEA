"""
atenea/ai.py — Unified LLM Interface

All AI calls in Atenea go through this module. It wraps litellm to provide:
- A single call_llm() function that works with any provider (DeepSeek, Anthropic, OpenAI, local)
- Automatic JSON parsing with retry on parse failure
- Language detection (langdetect with LLM fallback)
- Configurable via config/models.py globals + per-call overrides

To change which model is used for a task, edit config/models.py.
To change prompts, edit config/prompts.py.
"""

import json
import logging

from dotenv import load_dotenv
load_dotenv()

import litellm

from config import models as models_config

log = logging.getLogger(__name__)

# Suppress litellm's verbose logging
litellm.suppress_debug_info = True


def call_llm(prompt, model=None, temperature=None, max_tokens=None, task=None):
    """Call an LLM and return the text response.

    This is the single point of contact with LLM providers. Every
    AI-dependent function in Atenea calls this (or call_llm_json).

    Args:
        prompt: The complete prompt string to send.
        model: Model string in litellm format (e.g., "deepseek/deepseek-chat").
            If None, uses DEFAULT_MODEL from config/models.py.
        temperature: Float 0-2. If None, uses default for the task.
        max_tokens: Max tokens in response. If None, uses config default.
        task: Task name (e.g., "extraction_paths") for resolving model/temp
            from config. Takes precedence over model/temperature if set.

    Returns:
        str — the model's text response.

    Raises:
        Exception: On API errors after retries are exhausted.
    """
    # Resolve model and temperature from task config if provided
    if task:
        model = model or models_config.get_model(task)
        temperature = temperature if temperature is not None else models_config.get_temperature(task)
    else:
        model = model or models_config.DEFAULT_MODEL
        temperature = temperature if temperature is not None else 0.3

    max_tokens = max_tokens or models_config.MAX_TOKENS

    last_error = None
    for attempt in range(models_config.MAX_RETRIES + 1):
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=models_config.REQUEST_TIMEOUT,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            last_error = e
            if attempt < models_config.MAX_RETRIES:
                log.warning(f"LLM call failed (attempt {attempt + 1}): {e}")
            else:
                log.error(f"LLM call failed after {models_config.MAX_RETRIES + 1} attempts: {e}")
                raise last_error


def call_llm_json(prompt, model=None, temperature=None, task=None):
    """Call an LLM and parse the response as JSON.

    If the first response fails to parse as JSON, retries once with a
    correction prompt asking the model to fix its output.

    Args:
        prompt: The complete prompt string (should ask for JSON output).
        model: Model override (see call_llm).
        temperature: Temperature override (see call_llm).
        task: Task name for config resolution (see call_llm).

    Returns:
        dict or list — parsed JSON response.

    Raises:
        ValueError: If JSON parsing fails after retry.
    """
    raw = call_llm(prompt, model=model, temperature=temperature, task=task)

    # Try to parse directly
    parsed = _try_parse_json(raw)
    if parsed is not None:
        return parsed

    # Retry with correction prompt
    log.warning("First JSON parse failed, retrying with correction prompt")
    correction_prompt = (
        "Your previous response was not valid JSON. "
        "Please return ONLY valid JSON with no additional text, "
        "no markdown code blocks, no explanations.\n\n"
        f"Your previous response was:\n{raw}\n\n"
        "Please fix it and return ONLY the corrected JSON:"
    )
    raw_retry = call_llm(correction_prompt, model=model, temperature=0.0, task=task)
    parsed = _try_parse_json(raw_retry)
    if parsed is not None:
        return parsed

    raise ValueError(
        f"Failed to parse LLM response as JSON after retry.\n"
        f"Last response: {raw_retry[:500]}"
    )


def _try_parse_json(text):
    """Attempt to parse text as JSON, handling common LLM quirks.

    Handles:
    - Clean JSON
    - JSON wrapped in ```json ... ``` code blocks
    - JSON with leading/trailing text

    Returns:
        Parsed JSON (dict or list), or None if parsing fails.
    """
    # Strip markdown code blocks if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try to find JSON array or object in the text
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = cleaned.find(start_char)
        end = cleaned.rfind(end_char)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                pass

    return None


def detect_language(text):
    """Detect the language of a text fragment.

    Uses langdetect library. Falls back to "en" if detection fails.

    Args:
        text: Text fragment (at least a few sentences for accuracy).

    Returns:
        str — "es" for Spanish, "en" for English (or other ISO 639-1 codes).
    """
    try:
        from langdetect import detect
        lang = detect(text[:2000])  # First 2000 chars is enough
        # Normalize to our supported languages
        if lang.startswith("es"):
            return "es"
        return "en"
    except Exception:
        log.warning("Language detection failed, defaulting to 'en'")
        return "en"


def get_language_instruction(lang):
    """Get the language instruction string for a detected language.

    Args:
        lang: Language code ("es" or "en").

    Returns:
        str — instruction to include in prompts.
    """
    from config.prompts import LANGUAGE_INSTRUCTIONS
    return LANGUAGE_INSTRUCTIONS.get(lang, LANGUAGE_INSTRUCTIONS["en"])
