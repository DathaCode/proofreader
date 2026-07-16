# -*- coding: utf-8 -*-
"""
lang_detect.py — detect the script/language of a piece of text.

Used to route each proofreading request to the correct system prompt:
  * "si" — Sinhala   (U+0D80–U+0DFF)
  * "ta" — Tamil     (U+0B80–U+0BFF)
  * "en" — English / Latin (a–z, A–Z)

Rule: whichever Indic script has more characters wins (Sinhala on a tie, since
this is a Sinhala-first tool). Latin only wins when there is no Indic script at
all. Embedded English words inside Sinhala/Tamil text therefore do not flip the
language — the dominant script decides.
"""

import re

_SI = re.compile("[඀-෿]")   # Sinhala block
_TA = re.compile("[஀-௿]")   # Tamil block
_LA = re.compile("[A-Za-z]")          # Latin letters

SUPPORTED = ("si", "ta", "en")


def script_counts(text):
    text = text or ""
    return {
        "si": len(_SI.findall(text)),
        "ta": len(_TA.findall(text)),
        "en": len(_LA.findall(text)),
    }


def detect_language(text, default="si"):
    """Return 'si', 'ta', or 'en' for `text`.

    Empty / punctuation-only text returns `default`."""
    c = script_counts(text)
    si, ta, la = c["si"], c["ta"], c["en"]
    if si == 0 and ta == 0:
        return "en" if la > 0 else default
    # An Indic script is present — pick the larger; Sinhala wins ties.
    return "si" if si >= ta else "ta"


def normalize_lang(lang, default="si"):
    """Clamp an arbitrary lang hint to a supported value."""
    lang = (lang or "").strip().lower()[:2]
    return lang if lang in SUPPORTED else default
