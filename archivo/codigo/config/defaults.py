"""
config/defaults.py — Atenea Configuration Constants
"""

import os as _os

# ============================================================
# DATA DIRECTORY
# ============================================================

DEFAULT_DATA_DIR = _os.environ.get(
    "ATENEA_DATA_DIR",
    _os.path.expanduser("~/.atenea/data"),
)

# ============================================================
# 7+-2 RULE — Miller (1956)
# Sequences hold 5-9 connected nodes. Maps group 5-9 sequences.
# ============================================================

MIN_ELEMENTS = 5
MAX_ELEMENTS = 9

# ============================================================
# SM-2 SPACED REPETITION — Wozniak (1990)
# ============================================================

SM2_INITIAL_EF = 2.5
SM2_EF_MINIMUM = 1.3
SM2_INITIAL_INTERVAL_DAYS = 1.0
SM2_SECOND_INTERVAL_DAYS = 6.0
SM2_PASSING_QUALITY = 3

# ============================================================
# SESSION
# ============================================================

DEFAULT_QUESTIONS_PER_TEST = 25
