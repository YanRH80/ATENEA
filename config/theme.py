"""
config/theme.py — CLI Visual Theme

Color palette, status icons, and formatting constants for rich terminal output.
All CLI modules import from here to ensure visual consistency.
"""

# ============================================================
# STATUS COLORS — node/edge knowledge status
# ============================================================

STATUS_COLORS = {
    "unknown": "red",
    "testing": "yellow",
    "known": "green",
    "removed": "dim",
}

STATUS_ICONS = {
    "unknown": "\u2717",     # ✗
    "testing": "\u25cb",     # ○
    "known": "\u2713",       # ✓
    "removed": "\u2014",     # —
}

# ============================================================
# EVIDENCE LEVEL COLORS
# ============================================================

EVIDENCE_COLORS = {
    "1++": "bold green",
    "1+": "green",
    "1-": "yellow",
    "2++": "cyan",
    "2+": "blue",
    "2-": "yellow",
    "3": "magenta",
    "4": "dim",
    "E": "italic red",
}

# ============================================================
# PROBABILITY STRATA COLORS
# ============================================================

PROBABILITY_COLORS = {
    "always": "bold green",
    "certain": "green",
    "likely": "cyan",
    "even": "yellow",
    "unlikely": "magenta",
    "impossible": "red",
    "never": "bold red",
}

# ============================================================
# GENERAL UI
# ============================================================

ACCENT = "cyan"
HEADER = "bold white"
MUTED = "dim"
ERROR = "bold red"
SUCCESS = "bold green"
WARNING = "bold yellow"
INFO = "cyan"

# Borders and panels
PANEL_BORDER = "cyan"
TABLE_BORDER = "dim"

# ============================================================
# NAVIGATION
# ============================================================

NAV_PROMPT_STYLE = "bold cyan"
NAV_OPTION_NUMBER = "bold white"
NAV_OPTION_TEXT = "white"
NAV_HINT = "dim italic"

# ============================================================
# PROGRESS
# ============================================================

PROGRESS_BAR_STYLE = "cyan"
PROGRESS_COMPLETE_STYLE = "green"
PROGRESS_SPINNER = "dots"
