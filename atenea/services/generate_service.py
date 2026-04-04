"""
atenea/services/generate_service.py — Question generation (UI-agnostic)

Re-exports from atenea.generate for uniform service API.
generate.py is already 95% clean (no display imports).
"""

from atenea.generate import (  # noqa: F401
    run_generate,
    generate_questions,
    select_targets,
    retrieve_context,
    PATTERNS,
)
