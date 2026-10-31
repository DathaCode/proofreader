# -*- coding: utf-8 -*-
"""
gemini_web.py — proofreading engine for the web app.

Reuses the three-layer logic from proxy_server/proxy.py (pre-check from the
human corrections DB, few-shot injection, then Gemini) over the firewall-friendly
REST client (gemini_rest.py), in all three languages. Also resolves character
offsets for each error so the browser can highlight spans.

Long texts (like the LAN proxy) are split into paragraph/sentence-aligned parts
of ~`chunk_words` words that are checked IN PARALLEL and stitched back together,
so a full article no longer has to fit in one Gemini answer (which capped it at
10 errors and often timed out). A part that hits a transient Gemini error is
retried once instead of failing the whole check.

Returns the same normalized result dict the rest of the system already speaks,
plus two private keys the route strips before replying: "_usage" (summed token
usage, for cost tracking) and "_chunks".
"""

import re
import time
import difflib
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor

from gemini_rest import GeminiRest, GeminiRestError
from lang_detect import detect_language, normalize_lang

# Trailing instruction appended to each prompt, per language.
_TAIL = {
    "si": "\n\nSinhala text to proofread:\n",
    "ta": "\n\nTamil text to proofread:\n",
    "en": "\n\nEnglish text to proofread:\n",
}

# Native-language note + explanation field key for a pre-fixed (human-DB)
# correction, per language — English has no native explanation field of its
# own, so its note goes into explanation_en directly (expl_native is unused).
_PRECHECK_NOTE = {
    "si": ("මිනිස් සමාලෝචකයෙකු විසින් නිවැරදි කළ දෝෂයකි", "explanation_si"),
    "ta": ("மனிதப் பரிசோதகர் ஒருவரால் திருத்தப்பட்ட பிழை", "explanation_ta"),
    "en": ("Previously corrected by a human reviewer", "explanation_en"),
}

CONFIDENCE_THRESHOLD = 0.75
MAX_ERRORS = 10                 # Gemini errors kept per part (prompts cap at 10)
PART_ATTEMPTS = 2               # a part that hits a transient error is retried once
_TRANSIENT_HTTP = (408, 429, 500, 502, 503, 504)
# "punctuation" is what the English prompt emits; it used to be relabelled as
# spelling. The UI already colours it like grammar.
_VALID_TYPES = ("spelling", "grammar", "grammar_discord", "encoding_error", "punctuation")
_GRAMMAR_TYPES = ("grammar", "grammar_discord", "punctuation")

# Summary used when a text was checked in several parts (per-part summaries
# don't add up to a readable whole). {w} words, {p} parts, {n} issues.
_MULTI_SUMMARY = {
    "si": "වචන {w} ක් කොටස් {p} කින් පරීක්ෂා කළා — ගැටලු {n} ක් හමු විය.",
    "ta": "{w} சொற்கள் {p} பகுதிகளாகச் சரிபார்க்கப்பட்டன — {n} பிழை(கள்) கண்டறியப்பட்டன.",
    "en": "Checked {w} words in {p} parts — {n} issue(s) found.",
}
_PART_FAILED = {
    "si": "  ⚠️ කොටස් {f} ක් පරීක්ෂා කළ නොහැකි විය — නැවත උත්සාහ කරන්න.",
    "ta": "  ⚠️ {f} பகுதி(கள்) சரிபார்க்க முடியவில்லை — மீண்டும் முயற்சிக்கவும்.",
    "en": "  ⚠️ {f} of {p} part(s) could not be checked — try again.",
}

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

    # ----- speech-to-text (voice typing) ---------------------------------
    # Spoken-language hints, so the model writes the correct script. Tamil's
    # hint is deliberately more explicit than Sinhala/English: Tamil and
    # Sinhala are phonetically close and share a country context, and a
    # weakly-grounded prompt can drift into transliterating Tamil speech
    # into Sinhala letters (or plain Latin) instead of native Tamil script —
    # this forbids that outright rather than just naming the target script.
    _SPEECH_LANG = {
        "si": "The speaker is talking in Sinhala (සිංහල). Write it in Sinhala script.",
        "ta": ("The speaker is talking in TAMIL (தமிழ்), not Sinhala. Transcribe using "
               "native Tamil Unicode letters ONLY (அ-ஔ, க-ஹ, ொ/ோ/ெ/ே vowel signs, etc.). "
               "Do NOT write the words in Sinhala script, and do NOT romanize/transliterate "
               "Tamil into Latin letters — output real Tamil script text."),
        "en": "The speaker is talking in English. Write it in English.",
    }

    def transcribe(self, audio_b64, mime_type="audio/wav", lang=None):
        """Transcribe recorded speech via Gemini -> (text, token usage).
        `lang` (si/ta/en) is a hint from the UI's Text-language picker;
        None = let Gemini detect."""
        if self.client is None:
            raise RuntimeError(self.model_error or "Gemini model not ready")

        lang = normalize_lang(lang, default="") if lang else ""
        if lang in self._SPEECH_LANG:
            target = self._SPEECH_LANG[lang]
        else:
            target = ("The speaker may be using Sinhala, Tamil or English. "
                      "Detect which, and write it in that language's own native script "
                      "(Sinhala speech -> Sinhala Unicode, Tamil speech -> Tamil Unicode, "
                      "never cross-script transliteration).")

        prompt = (
            "You are a precise speech-to-text transcriber.\n"
            + target + "\n\n"
            "Rules:\n"
            "- Output ONLY the transcription text. No preamble, no quotes, no notes.\n"
            "- Do NOT translate. Keep the speaker's original language and script.\n"
            "- English words spoken inside Sinhala/Tamil speech stay in Latin script\n"
            "  (e.g. software, meeting, email).\n"
            "- Use natural punctuation and sentence breaks.\n"
            "- Transcribe only what is actually said — never invent or complete words.\n"
            "- If the audio is silent or unintelligible, output nothing at all.\n"
        )

        with self.sem:
            text, usage = self.client.transcribe_ex(prompt, audio_b64, mime_type=mime_type)
        return sanitize_input(text or "").strip(), usage

    # ----- core proofreading (three layers, language-aware) --------------
    def max_words(self):
        return int(self.cfg.get("max_words", 5000) or 5000)

    def proofread(self, text, lang=None):
        """Proofread `text` (up to max_words). `lang` (si/ta/en) forces a prompt;
        if omitted the language is auto-detected from the text's script.

        Long text is split into parts checked in parallel (bounded by
        max_concurrent). Every error carries start/end offsets into the
        returned `original` — the user's own (normalised) text, so learned
        corrections that were auto-fixed are highlighted too.
        """
        text = unicodedata.normalize("NFC", sanitize_input(text).strip())
        if not text:
            return {
                "errors": [], "corrected_text": "", "original": "",
                "lang": normalize_lang(lang), "detected_lang": normalize_lang(lang),
                "summary_native": "", "summary_si": "", "summary_en": "",
                "pre_fixed_count": 0, "stats": _stats("", []),
                "_usage": None, "_chunks": 0,
            }
        if self.client is None:
            raise RuntimeError(self.model_error or "Gemini model not ready")

        # Resolve target language: explicit override, else auto-detect.
        lang = normalize_lang(lang) if lang else detect_language(text)

        # Shared by every part: learned corrections for THIS language only.
        ctx = {
            "lang": lang,
            "precheck": self.db.get_precheck_map(lang),
            "inject": self.db.export_for_injection(int(self.cfg.get("inject_top_n", 40)), lang),
            "prompt": self.prompts.get(lang) or self.cfg.get_prompt(lang),
            "threshold": float(self.cfg.get("confidence_threshold", CONFIDENCE_THRESHOLD)),
        }

        chunks = _split_chunks(text, int(self.cfg.get("chunk_words", 250) or 250))
        offsets, pos = [], 0
        for c in chunks:
            offsets.append(pos)
            pos += len(c)

        def run(i):
            try:
                return self._proofread_chunk(chunks[i], offsets[i], ctx), None
            except Exception as e:          # one bad part must not sink the rest
                return None, e

        if len(chunks) == 1:
            results = [run(0)]
        else:
            workers = max(1, min(len(chunks), int(self.cfg.get("max_concurrent", 4))))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(run, range(len(chunks))))

        failed = [e for r, e in results if e is not None]
        if len(failed) == len(results):
            raise failed[0]

        errors, parts, usage, pre_fixed, summaries = [], [], None, 0, []
        for chunk, (r, _e) in zip(chunks, results):
            if r is None:
                parts.append(chunk)         # an unchecked part stays as typed
                continue
            errors.extend(r["errors"])
            parts.append(r["corrected"])
            pre_fixed += r["pre_fixed"]
            summaries.append(r["summaries"])
            usage = _add_usage(usage, r["usage"])

        if len(chunks) == 1:
            sm = dict(summaries[0])
        else:
            fmt = {"w": len(text.split()), "p": len(chunks), "n": len(errors)}
            sm = {"native": _MULTI_SUMMARY[lang].format(**fmt),
                  "si": _MULTI_SUMMARY["si"].format(**fmt) if lang == "si" else "",
                  "ta": _MULTI_SUMMARY["ta"].format(**fmt) if lang == "ta" else "",
                  "en": _MULTI_SUMMARY["en"].format(**fmt)}
        if failed:
            fmt = {"f": len(failed), "p": len(chunks)}
            sm["native"] += _PART_FAILED[lang].format(**fmt)
            sm["en"] += _PART_FAILED["en"].format(**fmt)

        return {
            "ok": True,
            "lang": lang,
            "detected_lang": lang,
            "errors": errors,
            "corrected_text": "".join(parts),
            "original": text,
            "summary_native": sm["native"],
            "summary_si": sm["si"],
            "summary_ta": sm["ta"],
            "summary_en": sm["en"],
            "pre_fixed_count": pre_fixed,
            "parts": len(chunks),
            "parts_failed": len(failed),
            "stats": _stats(text, errors, pre_fixed),
            "_usage": usage,
            "_chunks": len(chunks),
        }

    def _proofread_chunk(self, chunk, offset, ctx):
        """Check one part. `offset` = its position in the full input text."""
        lang = ctx["lang"]
        lead = chunk[:len(chunk) - len(chunk.lstrip())]
        trail = chunk[len(chunk.rstrip()):]
        original = chunk.strip()
        base = offset + len(lead)               # where `original` starts in the input
        if not original:
            return {"errors": [], "corrected": chunk, "pre_fixed": 0, "usage": None,
                    "summaries": {"native": "", "si": "", "ta": "", "en": ""}}

        # LAYER 1 — instant fixes from the human corrections DB (this language).
        work, pre_fixed = original, []
        expl_native, expl_key = _PRECHECK_NOTE.get(lang, _PRECHECK_NOTE["si"])
        for wrong, correct in ctx["precheck"].items():
            if wrong and wrong in work:
                work = work.replace(wrong, correct)
                entry = {
                    "original": wrong, "correction": correct, "type": "spelling",
                    "confidence": 1.0, "source": "human_db",
                    "explanation_en": "Previously corrected by a human reviewer",
                }
                entry[expl_key] = expl_native
                entry["explanation_native"] = expl_native
                pre_fixed.append(entry)

        # LAYER 2 — inject learned corrections + protect embedded English.
        english_note = ""
        if lang in ("si", "ta"):
            english = sorted(set(re.findall(r"[A-Za-z]+", work)))
            if english:
                english_note = ("\n\nCRITICAL: These English words appear in the text. "
                                "They are ALL valid. NEVER flag them: " + ", ".join(english))
        prompt = ctx["prompt"] + ctx["inject"] + english_note + _TAIL.get(lang, _TAIL["si"]) + work

        # LAYER 3 — Gemini over plain HTTPS REST. Latency varies a lot (thinking
        # models especially), so a timeout / overload / rate-limit on one part is
        # retried once instead of failing the user's whole check.
        for attempt in range(PART_ATTEMPTS):
            try:
                with self.sem:
                    raw, usage = self.client.generate_content_ex(
                        prompt, temperature=0.05, json_mode=True)
                break
            except GeminiRestError as e:
                if attempt + 1 >= PART_ATTEMPTS or not _is_transient(e):
                    raise
                time.sleep(3)
        data = _parse_json(raw or "", work)

        raw_errors = data.get("errors")
        if raw_errors is None:
            raw_errors = data.get("corrections")
        gemini_errors = []
        for e in (raw_errors or []):
            if not isinstance(e, dict):
                continue
            conf = _clamp(e.get("confidence", 1.0))
            if conf < ctx["threshold"]:
                continue
            etype = e.get("type", "spelling")
            if etype not in _VALID_TYPES:
                etype = "spelling"
            expl_n = (e.get("explanation_si") or e.get("explanation_ta")
                      or e.get("explanation_en") or "")
            gemini_errors.append({
                "original": str(e.get("original", "")),
                "correction": str(e.get("correction", "")),
                "type": etype,
                "explanation_native": str(expl_n),
                "explanation_si": str(e.get("explanation_si", "")),
                "explanation_ta": str(e.get("explanation_ta", "")),
                "explanation_en": str(e.get("explanation_en", "")),
                "confidence": conf,
            })
        gemini_errors.sort(key=lambda x: x.get("confidence", 1), reverse=True)
        errors = pre_fixed + gemini_errors[:MAX_ERRORS]

        # Offsets into the ORIGINAL part (what the user typed and the browser
        # highlights), shifted to whole-input positions; then document order.
        _locate(errors, original, base)
        errors.sort(key=lambda x: (x["start"] is None, x["start"] or 0))

        corrected = str(data.get("corrected_text", work)) or work
        corrected = _restore_linebreaks(work, corrected)

        native = (data.get("summary_native") or data.get("summary_si")
                  or data.get("summary_ta") or data.get("summary_en") or "")
        return {
            "errors": errors,
            "corrected": lead + corrected + trail,
            "pre_fixed": len(pre_fixed),
            "usage": usage,
            "summaries": {"native": str(native),
                          "si": str(data.get("summary_si", "")),
                          "ta": str(data.get("summary_ta", "")),
                          "en": str(data.get("summary_en", ""))},
        }


# ----- helpers (ported from proxy.py + gemini_engine.py) -----------------
def _locate(errors, text, base=0):
    """Set start/end char offsets (shifted by `base`) of each error's `original`
    in `text`. Each error claims its next unclaimed occurrence, so repeated
    words don't all highlight the same span."""
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
                e["start"], e["end"] = base + span[0], base + span[1]
                break
            start_at = idx + 1


def _split_chunks(text, max_words):
    """Split text into consecutive substrings of about `max_words` words.

    "".join(chunks) == text exactly. Cuts prefer paragraph breaks, then sentence
    ends, then any word boundary — never in the middle of a word.
    """
    max_words = max(20, int(max_words or 250))
    words = [m.start() for m in re.finditer(r"\S+", text)]
    if len(words) <= max_words:
        return [text]
    para = {m.end() for m in re.finditer(r"\n\s*", text)}
    sent = {m.end() for m in re.finditer(r"[.!?෴।]\s+", text)}
    chunks, i, start_pos = [], 0, 0
    while i < len(words):
        end_i = i + max_words
        if end_i >= len(words):
            chunks.append(text[start_pos:])
            break
        cut = None
        floor = i + max_words // 2        # never make a part smaller than half
        for boundaries in (para, sent):
            for k in range(end_i, floor, -1):
                if words[k] in boundaries:
                    cut = k
                    break
            if cut is not None:
                break
        if cut is None:
            cut = end_i
        chunks.append(text[start_pos:words[cut]])
        start_pos, i = words[cut], cut
    return chunks


def _is_transient(e):
    """Network error / timeout (no HTTP status) or an overload/rate-limit status."""
    return getattr(e, "status", None) in (None,) + _TRANSIENT_HTTP


def _add_usage(total, u):
    if not u:
        return total
    if total is None:
        return dict(u)
    for k in ("in", "audio", "out"):
        total[k] = total.get(k, 0) + u.get(k, 0)
    return total


def _snap_to_space(s, p):
    if p <= 0 or p >= len(s):
        return p
    if s[p - 1].isspace() or s[p].isspace():
        return p
    for d in range(1, 30):
        if p - d > 0 and s[p - d].isspace():
            return p - d + 1
        if p + d < len(s) and s[p + d].isspace():
            return p + d + 1
    return p


def _restore_linebreaks(original, corrected):
    """Re-apply the input's line breaks if the model returned one paragraph."""
    if "\n" not in original or "\n" in corrected:
        return corrected
    blocks = difflib.SequenceMatcher(None, original, corrected,
                                     autojunk=False).get_matching_blocks()

    def map_pos(oi):
        after = len(corrected)
        for i, j, size in blocks:
            if size == 0:
                continue
            if oi < i:
                return j
            if i <= oi < i + size:
                return j + (oi - i)
            after = j + size
        return after

    positions = sorted(
        p for p in {_snap_to_space(corrected, map_pos(i))
                    for i, ch in enumerate(original) if ch == "\n"}
        if 0 < p < len(corrected))
    if not positions:
        return corrected
    out, prev = [], 0
    for p in positions:
        if p <= prev:
            continue
        out.append(corrected[prev:p].rstrip())
        prev = p
    out.append(corrected[prev:].lstrip())
    return "\n".join(out)


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
