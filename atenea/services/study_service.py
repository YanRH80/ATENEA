"""
atenea/services/study_service.py — Knowledge extraction (UI-agnostic)

Re-exports from atenea.study for uniform service API.
study.py is already 95% clean (no display imports).
"""

from atenea.study import (  # noqa: F401
    run_study,
    condense_to_knowledge,
    merge_knowledge,
    load_source_text,
)
