"""
atenea/web/theme.py — Web UI color palette and style constants

Derived from config/theme.py (CLI) but adapted for web/CSS.
"""

# Primary palette
PRIMARY = "#2563eb"       # Blue-600 — accent, links, active
PRIMARY_LIGHT = "#3b82f6" # Blue-500
PRIMARY_DARK = "#1d4ed8"  # Blue-700

# Status colors (SM-2)
KNOWN = "#16a34a"         # Green-600
TESTING = "#eab308"       # Yellow-500
UNKNOWN = "#dc2626"       # Red-600

# Neutral
BG = "#0f172a"            # Slate-900 — page background
CARD_BG = "#1e293b"       # Slate-800 — card background
SURFACE = "#334155"       # Slate-700 — elevated surface
TEXT = "#f1f5f9"          # Slate-100 — primary text
TEXT_MUTED = "#94a3b8"    # Slate-400 — secondary text
BORDER = "#475569"        # Slate-600

# Feedback
SUCCESS = "#16a34a"
ERROR = "#dc2626"
WARNING = "#eab308"
INFO = "#2563eb"

# Evidence level colors (matching SIGN/NICE)
EVIDENCE_COLORS = {
    "1++": KNOWN,
    "1+": KNOWN,
    "1-": "#22c55e",
    "2++": TESTING,
    "2+": TESTING,
    "2-": "#f59e0b",
    "3": WARNING,
    "4": ERROR,
    "E": TEXT_MUTED,
}

# Graph node colors by status
NODE_COLORS = {
    "known": KNOWN,
    "testing": TESTING,
    "unknown": ERROR,
}

# Common Tailwind-like classes
CARD_CLASSES = "bg-slate-800 rounded-lg shadow-md"
HEADER_CLASSES = "text-2xl font-bold text-slate-100"
SUBHEADER_CLASSES = "text-lg font-semibold text-slate-300"
MUTED_CLASSES = "text-sm text-slate-400"
