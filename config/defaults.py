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

# ============================================================
# CHUNKING
# ============================================================

PARAGRAPH_SEPARATOR = "\n\n"
MAX_PARAGRAPH_CHARS = 1500   # Split paragraph if exceeds this
MAX_CHUNK_CHARS = 6000       # Max chars per LLM chunk
MIN_CHUNK_CHARS = 200        # Discard fragments smaller than this

# ============================================================
# PROBABILITY STRATA — for edge associations
# ============================================================

PROB_STRATA = {
    "always": 1.0,       # Logical implication, P=1
    "certain": 0.95,     # Almost always
    "likely": 0.75,      # Most of the time
    "even": 0.50,        # Could go either way
    "unlikely": 0.25,    # Rarely
    "impossible": 0.05,  # Almost never
    "never": 0.0,        # Logical negation, P=0
}

# ============================================================
# EVIDENCE LEVELS — SIGN/NICE standard
# ============================================================

EVIDENCE_LEVELS = {
    "1++": "Metaanalisis/RS/ECA alta calidad, muy bajo riesgo de sesgo",
    "1+":  "Estudios bien realizados, bajo riesgo de sesgo",
    "1-":  "Estudios con alto riesgo de sesgo",
    "2++": "Cohortes/casos-controles alta calidad, bajo riesgo de sesgo",
    "2+":  "Cohortes/casos-controles buena calidad",
    "2-":  "Cohortes/casos-controles alto riesgo de sesgo",
    "3":   "Estudios no analiticos (series de casos)",
    "4":   "Opinion de expertos",
}

RECOMMENDATION_GRADES = {
    "A": "Basado en evidencia 1++/1+ directamente aplicable",
    "B": "Basado en evidencia 2++ o extrapolada de 1",
    "C": "Basado en evidencia 2+ o extrapolada de 2++",
    "D": "Basado en evidencia 3-4 o extrapolada de 2+",
}

# ============================================================
# ZOTERO — item_type → default evidence level
# ============================================================

ZOTERO_TYPE_TO_EVIDENCE = {
    "journalArticle": "2+",
    "conferencePaper": "3",
    "book": "4",
    "bookSection": "4",
    "thesis": "3",
    "report": "3",
    "webpage": "4",
    "preprint": "3",
    "review": "1+",
    "encyclopediaArticle": "4",
}

# ============================================================
# CITATION FORMAT
# ============================================================

DEFAULT_CITATION_STYLE = "vancouver"
