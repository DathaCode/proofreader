# -*- coding: utf-8 -*-
"""
theme.py — modern colour palette for the Sinhala Proofreader.

Colours are CustomTkinter (light, dark) tuples so a single definition looks good
in both themes. tk.Text needs plain colours, so result_colors() resolves them
for the current appearance mode.
"""

import customtkinter as ctk

# Accent / action colours
ACCENT        = "#3b82f6"
ACCENT_HOVER  = "#2563eb"
SUCCESS       = "#16a34a"
SUCCESS_HOVER = "#15803d"
DANGER        = "#dc2626"
DANGER_HOVER  = "#b91c1c"
WARNING       = "#d97706"

# Soft tinted backgrounds for pills / banners / chips: (light, dark)
ACCENT_SOFT   = ("#e8f0fe", "#162641")
SUCCESS_SOFT  = ("#e6f6ec", "#12301f")
DANGER_SOFT   = ("#fdecec", "#3a1818")
WARNING_SOFT  = ("#fdf3e1", "#3a2a0f")
SUCCESS_TEXT  = ("#15803d", "#4ade80")
DANGER_TEXT   = ("#b91c1c", "#fca5a5")
WARNING_TEXT  = ("#b45309", "#fbbf24")
ACCENT_TEXT   = ("#1d4ed8", "#93b4ff")

# Neutral (secondary) buttons
NEUTRAL       = ("#e2e8f0", "#252b36")
NEUTRAL_HOVER = ("#cbd5e1", "#323a48")

# Surfaces
WINDOW_BG = ("#eef2f8", "#0f1217")
HEADER_BG = ("#ffffff", "#171b22")
CARD_BG   = ("#ffffff", "#1a1f28")
BAR_BG    = ("#f3f6fb", "#141821")
BORDER    = ("#dbe2ec", "#2a3140")

# Text
TEXT      = ("#1f2733", "#e8edf4")
MUTED     = ("#64748b", "#9aa6b6")

# Error highlight backgrounds (v4 solid style; kept for compatibility)
SPELL_BG   = "#ef4444"
GRAMMAR_BG = "#f59e0b"

# Corner radii
R_CARD = 14
R_BTN = 9
R_BOX = 10


def result_colors():
    """Plain colours for the tk.Text highlight widget, per appearance mode.

    Errors are shown as a soft tint + coloured, underlined text (easier to read
    than white-on-red blocks); "focus" marks the issue the user selected."""
    if ctk.get_appearance_mode() == "Dark":
        return {"bg": "#161a21", "fg": "#e8edf4", "insert": "#e8edf4", "sel": "#2b5cab",
                "spell_bg": "#4a1d22", "spell_fg": "#ffb4b4",
                "grammar_bg": "#47330f", "grammar_fg": "#ffd27a",
                "focus_bg": "#2f5fd0", "focus_fg": "#ffffff"}
    return {"bg": "#fbfcff", "fg": "#1f2733", "insert": "#1f2733", "sel": "#bcd3f5",
            "spell_bg": "#fde3e3", "spell_fg": "#b4232a",
            "grammar_bg": "#fdf0d5", "grammar_fg": "#9a5b00",
            "focus_bg": "#2563eb", "focus_fg": "#ffffff"}
