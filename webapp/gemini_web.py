# -*- coding: utf-8 -*-
"""
gemini_web.py — proofreading engine for the web app.

Reuses the exact three-layer logic from proxy_server/proxy.py (pre-check from the
human corrections DB, few-shot injection, then Gemini) over the firewall-friendly
REST client (gemini_rest.py). Also resolves character offsets for each error so
the browser can highlight spans (ported from engine/gemini_engine._locate).

Returns the same normalized result dict the rest of the system already speaks.
"""

import re
import threading
import unicodedata

from gemini_rest import GeminiRest, GeminiRestError
from lang_detect import detect_language, normalize_lang

# Trailing instruction appended to each prompt, per language.
_TAIL = {
    "si": "\n\nSinhala text to proofread:\n",
    "ta": "\n\nTamil text to proofread:\n",
    "en": "\n\nEnglish text to proofread:\n",
}

CONFIDENCE_THRESHOLD = 0.75
MAX_ERRORS = 10
_VALID_TYPES = ("spelling", "grammar", "grammar_discord", "encoding_error")
_GRAMMAR_TYPES = ("grammar", "grammar_discord")

# Strip HTML tags/scripts before anything reaches Gemini (input sanitization).
_TAG_RE = re.compile(r"<[^>]*>")


def sanitize_input(text):
    """Remove HTML markup and control noise from user text."""
    text = _TAG_RE.sub("", text or "")
    # Drop NULs and other control chars except tab/newline.
    text = "".join(ch for ch in text if ch >= " " or ch in "\t\n\r")
    return text


class WebProofreader:
    """Wraps the corrections DB + REST Gemini client for one config snapshot."""

    def __init__(self, cfg, db):
        self.cfg = cfg
        self.db = db
        self.client = None
        self.model_error = ""
        self.available_models = []
        self._models_tried = False
        self.sem = threading.Semaphore(int(cfg.get("max_concurrent", 4)))
        self.prompts = {}
        self.reload_model()

    # ----- lifecycle -----------------------------------------------------
    def reload_model(self):
        """(Re)build the REST client + reload all per-language prompts."""
        self.prompts = {l: self.cfg.get_prompt(l) for l in ("si", "ta", "en")}
        self.sem = threading.Semaphore(int(self.cfg.get("max_concurrent", 4)))
        self._models_tried = False
        key = self.cfg.get_api_key()
        if not key:
            self.client = None
            self.model_error = "No API key set (edit api_key.txt or use the admin panel)"
            return
        self.client = GeminiRest(
            key,
            self.cfg.get("model", "gemini-2.5-flash"),
            timeout=int(self.cfg.get("request_timeout", 60)),
        )
        self.model_error = ""

    def refresh_models(self):
        """Fetch usable models for this key. Returns "" on success, else error."""
        self._models_tried = True
        if self.client is None:
            self.available_models = []
            return self.model_error or "No API key set"
        try:
            self.available_models = self.client.list_models()
            return ""
        except GeminiRestError as e:
            return e.message

    def ensure_valid_model(self):
        """Switch to the best available model if the configured one is missing."""
        if not self.available_models:
            return None
        if self.cfg.get("model", "") in self.available_models:
            return None
        pick = _pick_best_model(self.available_models)
        if not pick:
            return None
        self.cfg.set("model", pick)
        self.cfg.save()
        self.reload_model()
        return pick

    def test_key(self):
        """Run a real test proofread. Returns (ok, message)."""
        self.reload_model()
        if self.client is None:
            return False, self.model_error or "No API key set"
        try:
            result = self.proofread("ලංකාවේ අද්‍යාපන ප්‍රශ්ණ ගොඩක් තිබේ.")
            n = len(result.get("errors", []))
            return True, "OK — test proofread succeeded (%d errors found)" % n
        except Exception as e:
            return False, str(e)[:240]

    # ----- core proofreading (three layers, language-aware) --------------
    def proofread(self, text, lang=None):
        """Proofread `text`. `lang` (si/ta/en) forces a prompt; if omitted the
        language is auto-detected from the text's script."""
        text = unicodedata.normalize("NFC", sanitize_input(text).strip())
        if not text:
            return {
                "errors": [], "corrected_text": "", "original": "",
                "lang": normalize_lang(lang), "detected_lang": normalize_lang(lang),
                "summary_native": "", "summary_si": "", "summary_en": "",
                "pre_fixed_count": 0, "stats": _stats("", []),
            }
        if self.client is None:
            raise RuntimeError(self.model_error or "Gemini model not ready")

        # Resolve target language: explicit override, else auto-detect.
        if lang:
            lang = normalize_lang(lang)
        else:
            lang = detect_language(text)

        # LAYER 1 + 2 (self-learning corrections DB) apply to Sinhala only —
        # the shared DB is Sinhala-tuned. Tamil/English go straight to Gemini.
        pre_fixed = []
        inject_block = ""
        if lang == "si":
            for wrong, correct in self.db.get_precheck_map().items():
                if wrong and wrong in text:
                    text = text.replace(wrong, correct)
                    pre_fixed.append({
                        "original": wrong, "correction": correct, "type": "spelling",
                        "confidence": 1.0, "source": "human_db",
                        "explanation_si": "මිනිස් සමාලෝචකයෙකු විසින් නිවැරදි කළ දෝෂයකි",
                        "explanation_en": "Previously corrected by a human reviewer",
                    })
            inject_block = self.db.export_for_injection(int(self.cfg.get("inject_top_n", 40)))

        # Protect embedded English words for Indic-script prompts only.
        english_note = ""
        if lang in ("si", "ta"):
            english = sorted(set(re.findall(r"[A-Za-z]+", text)))
            if english:
                english_note = ("\n\nCRITICAL: These English words appear in the text. "
                                "They are ALL valid. NEVER flag them: " + ", ".join(english))

        base_prompt = self.prompts.get(lang) or self.cfg.get_prompt(lang)
        prompt = base_prompt + inject_block + english_note + _TAIL.get(lang, _TAIL["si"]) + text

        # LAYER 3 — Gemini over plain HTTPS REST.
        with self.sem:
            raw = self.client.generate_content(prompt, temperature=0.05, json_mode=True)
        data = _parse_json(raw or "", text)

        threshold = float(self.cfg.get("confidence_threshold", CONFIDENCE_THRESHOLD))
        raw_errors = data.get("errors")
        if raw_errors is None:
            raw_errors = data.get("corrections")
        raw_errors = raw_errors or []
        gemini_errors = []
        for e in raw_errors:
            if not isinstance(e, dict):
                continue
            conf = _clamp(e.get("confidence", 1.0))
            if conf < threshold:
                continue
            etype = e.get("type", "spelling")
            if etype not in _VALID_TYPES:
                etype = "spelling"
            expl_native = (e.get("explanation_si") or e.get("explanation_ta")
                           or e.get("explanation_en") or "")
            gemini_errors.append({
                "original": str(e.get("original", "")),
                "correction": str(e.get("correction", "")),
                "type": etype,
                "explanation_native": str(expl_native),
                "explanation_si": str(e.get("explanation_si", "")),
                "explanation_ta": str(e.get("explanation_ta", "")),
                "explanation_en": str(e.get("explanation_en", "")),
                "confidence": conf,
            })

        # Give pre-fixed (Sinhala) errors a native explanation field too.
        for e in pre_fixed:
            e.setdefault("explanation_native", e.get("explanation_si", ""))

        all_errors = pre_fixed + gemini_errors
        all_errors.sort(key=lambda x: x.get("confidence", 1), reverse=True)
        all_errors = all_errors[:MAX_ERRORS]

        corrected = str(data.get("corrected_text", text)) or text
        _locate(all_errors, text)

        summary_native = (data.get("summary_native") or data.get("summary_si")
                          or data.get("summary_ta") or "")
        if not summary_native:  # English (and any prompt that only emits summary_en)
            summary_native = data.get("summary_en", "")
        stats = _stats(text, all_errors, len(pre_fixed))
        return {
            "ok": True,
            "lang": lang,
            "detected_lang": lang,
            "errors": all_errors,
            "corrected_text": corrected,
            "original": text,
            "summary_native": str(summary_native),
            "summary_si": str(data.get("summary_si", "")),
            "summary_ta": str(data.get("summary_ta", "")),
            "summary_en": str(data.get("summary_en", "")),
            "pre_fixed_count": len(pre_fixed),
            "stats": stats,
        }


# ----- helpers (ported from proxy.py + gemini_engine.py) -----------------
def _locate(errors, text):
    """Set start/end char offsets of each error's `original` in text.

    Each error claims its next unclaimed occurrence, so repeated words don't
    all highlight the same span. Pre-fixed words are already replaced and won't
    locate — that's expected (highlighting shows remaining Gemini spans)."""
    claimed = []
    for e in errors:
        orig = e.get("original", "")
        e["start"], e["end"] = None, None
        if not orig:
            continue
        start_at = 0
        while True:
            idx = text.find(orig, start_at)
            if idx == -1:
                break
            span = (idx, idx + len(orig))
            if not any(span[0] < c[1] and span[1] > c[0] for c in claimed):
                claimed.append(span)
                e["start"], e["end"] = span
                break
            start_at = idx + 1


def _pick_best_model(models):
    prefs = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash-001",
             "gemini-2.0-flash"]
    for p in prefs:
        if p in models:
            return p
    skip = ("lite", "exp", "thinking", "8b", "preview")
    for m in models:
        low = m.lower()
        if "flash" in low and not any(s in low for s in skip):
            return m
    for m in models:
        if "flash" in m.lower():
            return m
    return models[0] if models else None


def _clamp(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.8


def _stats(text, errors, pre_fixed=0):
    return {
        "total_words": len(text.split()),
        "errors_found": len(errors),
        "spell_errors": sum(1 for e in errors if e.get("type") == "spelling"),
        "grammar_errors": sum(1 for e in errors if e.get("type") in _GRAMMAR_TYPES),
        "encoding_errors": sum(1 for e in errors if e.get("type") == "encoding_error"),
        "pre_fixed": pre_fixed,
    }


def _parse_json(raw, fallback_text):
    import json
    cleaned = (raw or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    return {"errors": [], "corrected_text": fallback_text,
            "summary_si": "ප්‍රතිචාරය විග්‍රහ කළ නොහැකි විය",
            "summary_en": "Could not parse the model response"}
