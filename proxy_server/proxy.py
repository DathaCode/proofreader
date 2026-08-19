# -*- coding: utf-8 -*-
"""
proxy.py — Sinhala Proofreader Control PC proxy server.

LAN clients POST text here; this server calls Gemini (the only machine that needs
internet) with the shared self-learning corrections DB applied, and returns
structured results. Also serves an /admin web panel.

Run:  python proxy.py     (or START_PROXY.bat)
"""

import os
import re
import csv
import json
import time
import threading
import unicodedata
from datetime import datetime

from flask import Flask, request, jsonify

from config_proxy import (
    ProxyConfig, BASE_DIR, DATA_DIR, CORRECTIONS_PATH, LOG_PATH,
)
from corrections_db import CorrectionsDB
from usage_logger import UsageLogger
from admin_panel import admin_bp
from gemini_rest import GeminiRest, GeminiRestError

CONFIDENCE_THRESHOLD = 0.75
MAX_ERRORS = 10
_VALID_TYPES = ("spelling", "grammar", "grammar_discord", "encoding_error")


class ProxyState:
    """Shared, hot-reloadable server state used by routes + admin panel."""

    def __init__(self):
        self.cfg = ProxyConfig()
        self.db = CorrectionsDB(CORRECTIONS_PATH)
        self.logger = UsageLogger(LOG_PATH)
        self.prompt = self.cfg.get_prompt()
        self.client = None
        self.model_error = ""
        self.available_models = []   # populated lazily / on refresh_models()
        self._models_tried = False   # avoid re-hitting the API on every page load
        self.sem = threading.Semaphore(int(self.cfg.get("max_concurrent", 4)))
        self.reload_model()

    def reload_model(self):
        """(Re)build the Gemini REST client from the current key + model."""
        key = self.cfg.get_api_key()
        self.prompt = self.cfg.get_prompt()
        self.sem = threading.Semaphore(int(self.cfg.get("max_concurrent", 4)))
        self._models_tried = False   # key/model may have changed — allow one retry
        if not key:
            self.client = None
            self.model_error = "No API key set (edit api_key.txt or use the admin panel)"
            return
        # Building the client never hits the network, so it can't fail here;
        # validity is proven by Test Key / the first real request.
        self.client = GeminiRest(
            key,
            self.cfg.get("model", "gemini-2.5-flash"),
            timeout=int(self.cfg.get("request_timeout", 60)),
        )
        self.model_error = ""

    def refresh_models(self):
        """Fetch the models this key can use. Returns "" on success, else an error."""
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
        """If the configured model isn't in the available list, switch to the best
        available one (and persist it). Returns the new model name if changed."""
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

    # ----- core proofreading --------------------------------------------
    def proofread(self, text):
        text = unicodedata.normalize("NFC", (text or "").strip())
        if not text:
            return {"errors": [], "corrected_text": "", "summary_si": "",
                    "summary_en": "", "pre_fixed_count": 0,
                    "stats": _stats(text, [])}
        if self.client is None:
            raise RuntimeError(self.model_error or "Gemini model not ready")

        # LAYER 1 — pre-check from the human corrections DB.
        pre_fixed = []
        for wrong, correct in self.db.get_precheck_map().items():
            if wrong and wrong in text:
                text = text.replace(wrong, correct)
                pre_fixed.append({
                    "original": wrong, "correction": correct, "type": "spelling",
                    "confidence": 1.0, "source": "human_db",
                    "explanation_si": "මිනිස් සමාලෝචකයෙකු විසින් නිවැරදි කළ දෝෂයකි",
                    "explanation_en": "Previously corrected by a human reviewer",
                })

        # LAYER 2 — inject top corrections + protect English.
        inject_block = self.db.export_for_injection(int(self.cfg.get("inject_top_n", 40)))
        english = sorted(set(re.findall(r"[A-Za-z]+", text)))
        english_note = ""
        if english:
            english_note = ("\n\nCRITICAL: These English words appear in the text. "
                            "They are ALL valid. NEVER flag them: " + ", ".join(english))
        prompt = self.prompt + inject_block + english_note + "\n\nSinhala text to proofread:\n" + text

        # LAYER 3 — Gemini (plain HTTPS REST).
        with self.sem:
            raw = self.client.generate_content(prompt, temperature=0.05, json_mode=True)
        data = _parse_json(raw or "", text)

        raw_errors = data.get("errors")
        if raw_errors is None:
            raw_errors = data.get("corrections")
        raw_errors = raw_errors or []
        gemini_errors = []
        for e in raw_errors:
            if not isinstance(e, dict):
                continue
            conf = _clamp(e.get("confidence", 1.0))
            if conf < CONFIDENCE_THRESHOLD:
                continue
            etype = e.get("type", "spelling")
            if etype not in _VALID_TYPES:
                etype = "spelling"
            gemini_errors.append({
                "original": str(e.get("original", "")),
                "correction": str(e.get("correction", "")),
                "type": etype,
                "explanation_si": str(e.get("explanation_si", "")),
                "explanation_en": str(e.get("explanation_en", "")),
                "confidence": conf,
            })

        all_errors = pre_fixed + gemini_errors
        all_errors.sort(key=lambda x: x.get("confidence", 1), reverse=True)
        all_errors = all_errors[:MAX_ERRORS]

        corrected = str(data.get("corrected_text", text)) or text
        corrected = _restore_linebreaks(text, corrected)
        return {
            "errors": all_errors,
            "corrected_text": corrected,
            "summary_si": str(data.get("summary_si", "")),
            "summary_en": str(data.get("summary_en", "")),
            "pre_fixed_count": len(pre_fixed),
            "stats": _stats(text, all_errors, len(pre_fixed)),
        }

    # ----- transcription (voice typing) ---------------------------------
    def transcribe(self, audio_bytes, mime="audio/wav"):
        if self.client is None:
            raise RuntimeError(self.model_error or "Gemini model not ready")
        with self.sem:
            return self.client.transcribe_audio(audio_bytes, mime=mime)


# ----- helpers -----------------------------------------------------------
def _pick_best_model(models):
    """Choose a good default from a key's available models: a current 'flash'
    family model (great Sinhala + generous free-tier quota), avoiding lite/
    experimental/retired variants. Falls back to any flash, then the first model."""
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
        "grammar_errors": sum(1 for e in errors if e.get("type") in ("grammar", "grammar_discord")),
        "encoding_errors": sum(1 for e in errors if e.get("type") == "encoding_error"),
        "pre_fixed": pre_fixed,
    }


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
    """Re-apply the input's line breaks if the model returned a paragraph."""
    import difflib
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


def _parse_json(raw, fallback_text):
    cleaned = raw.strip()
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


# ----- Flask app ---------------------------------------------------------
STATE = ProxyState()

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
app.secret_key = os.urandom(24)
app.config["STATE"] = STATE
app.register_blueprint(admin_bp, url_prefix="/admin")


@app.route("/status")
def status():
    return jsonify({
        "status": "online",
        "model": STATE.cfg.get("model"),
        "corrections_total": STATE.db.get_stats()["total"],
        "model_ready": STATE.client is not None,
        "version": 2,
    })


@app.route("/proofread", methods=["POST"])
def proofread():
    t0 = time.time()
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    client_ip = request.remote_addr or "?"
    try:
        result = STATE.proofread(text)
        latency = int((time.time() - t0) * 1000)
        STATE.logger.log(client_ip, result["stats"]["total_words"],
                         result["stats"]["errors_found"],
                         result.get("pre_fixed_count", 0), latency, "ok")
        return jsonify(result)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        STATE.logger.log(client_ip, len(text.split()), 0, 0, latency, "error")
        return jsonify({
            "errors": [], "corrected_text": text,
            "summary_si": "Proxy දෝෂයකි", "summary_en": "Proxy error: %s" % str(e)[:160],
            "pre_fixed_count": 0, "stats": _stats(text, [])
        }), 500


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """Voice typing: client POSTs base64 audio, Gemini transcribes to Sinhala."""
    import base64
    t0 = time.time()
    payload = request.get_json(silent=True) or {}
    audio_b64 = payload.get("audio", "")
    mime = payload.get("mime", "audio/wav")
    client_ip = request.remote_addr or "?"
    if not audio_b64:
        return jsonify({"text": "", "error": "no audio"}), 400
    try:
        audio = base64.b64decode(audio_b64)
        text = STATE.transcribe(audio, mime=mime)
        latency = int((time.time() - t0) * 1000)
        STATE.logger.log(client_ip, len(text.split()), 0, 0, latency, "voice")
        return jsonify({"text": text})
    except Exception as e:
        return jsonify({"text": "", "error": str(e)[:200]}), 500


@app.route("/corrections")
def corrections():
    """Full corrections DB — used by clients to sync their local cache."""
    return jsonify(STATE.db.data)


@app.route("/record_correction", methods=["POST"])
def record_correction():
    payload = request.get_json(silent=True) or {}
    items = payload.get("corrections", [])
    saved = 0
    for c in items:
        res = STATE.db.record_correction(
            wrong=c.get("wrong", ""), correct=c.get("correct", ""),
            error_type=c.get("type", "spelling"),
            added_by=request.remote_addr or "client", source="client_edit",
            precheck_threshold=int(STATE.cfg.get("precheck_threshold", 5)),
        )
        if res.get("status") in ("added", "updated"):
            saved += 1
    return jsonify({"status": "ok", "saved": saved,
                    "total": STATE.db.get_stats()["total"]})


def main():
    host = STATE.cfg.get("host", "0.0.0.0")
    port = int(STATE.cfg.get("port", 8765))
    print("=" * 50)
    print(" Sinhala Proofreader Proxy Server")
    print(" Model:", STATE.cfg.get("model"),
          "| Key:", "SET" if STATE.cfg.get_api_key() else "MISSING")
    print(" Corrections:", STATE.db.get_stats()["total"])
    print(" Listening on http://%s:%d   (admin: /admin)" % (host, port))
    if STATE.model_error:
        print(" WARNING:", STATE.model_error)
    print("=" * 50)
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    main()
