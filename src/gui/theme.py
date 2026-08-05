"""
GUI Theme configuration.
Defines colors, font sizes, and UI dimensions.
"""

# ─── Base colours ────────────────────────────────────────────────────────────
BG_DARK     = "#181818"   # deep IDE background
BG_MID      = "#1e1e1e"   # standard editor background
BG_PANEL    = "#252526"   # panel/sidebar background
BG_HOVER    = "#2a2d2e"   # hover state
BORDER      = "#333333"   # subtle borders

# ─── Accent colours ──────────────────────────────────────────────────────────
ACCENT      = "#569cd6"   # IDE keyword blue
ACCENT_DIM  = "#4e8bc0"   # darker blue for hover
AMBER       = "#d7ba7d"   # soft amber/yellow (IDE strings/warnings)
RED         = "#f44747"   # IDE error red
GREEN       = "#4ec9b0"   # IDE types/classes (minty green)
GREEN_DIM   = "#608b4e"   # IDE comment green

# ─── Text colours ────────────────────────────────────────────────────────────
TEXT_PRIMARY   = "#cccccc"  # soft white
TEXT_SECONDARY = "#858585"  # IDE dim text / line numbers
TEXT_DIM       = "#606060"
TEXT_ACCENT    = ACCENT

# ─── Level colours ───────────────────────────────────────────────────────────
LEVEL_COLORS = {
    1: "#9cdcfe",   # variable blue
    2: "#4ec9b0",   # type teal
    3: "#569cd6",   # keyword blue (default)
    4: "#c586c0",   # control-flow magenta
}

# ─── Font sizes ──────────────────────────────────────────────────────────────
FONT_TITLE  = ("Consolas", 18, "bold")
FONT_HEADER = ("Consolas", 12, "bold")
FONT_BODY   = ("Consolas", 10)
FONT_SMALL  = ("Consolas", 9)
FONT_MONO   = ("Consolas", 10)
FONT_STAT   = ("Consolas", 26, "bold")

# ─── Sizes ───────────────────────────────────────────────────────────────────
CORNER_RADIUS = 4  # Corner radius for UI widgets
BUTTON_HEIGHT = 36

