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
import json
import time
import threading
import unicodedata
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from flask import Flask, request, jsonify

from config_proxy import (
    ProxyConfig, BASE_DIR, CORRECTIONS_PATH, LOG_PATH, USAGE_DB_PATH,
)
from corrections_db import CorrectionsDB
from usage_store import UsageStore
from admin_panel import admin_bp
from gemini_rest import GeminiRest, GeminiRestError

CONFIDENCE_THRESHOLD = 0.75
MAX_ERRORS_PER_CHUNK = 25       # v4 capped the WHOLE text at 10 errors
PART_ATTEMPTS = 2               # a part that hits a transient error is retried once
_TRANSIENT_HTTP = (408, 429, 500, 502, 503, 504)
API_VERSION = 3                 # /status "version": 3 = chunking + identity
_VALID_TYPES = ("spelling", "grammar", "grammar_discord", "encoding_error")


class ProxyState:
    """Shared, hot-reloadable server state used by routes + admin panel."""

    def __init__(self):
        self.cfg = ProxyConfig()
        self.started_at = time.time()
        self.db = CorrectionsDB(CORRECTIONS_PATH)
        self.usage = UsageStore(
            USAGE_DB_PATH,
            server_name_fn=self.cfg.server_name,
            pricing_fn=lambda: self.cfg.get("pricing") or {},
            legacy_csv=LOG_PATH,
        )
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
        """Proofread `text` of any length (up to max_words).

        Long text is split into paragraph/sentence-aligned chunks of about
        `chunk_words` words that are checked IN PARALLEL (bounded by
        max_concurrent), then stitched back together. Every error carries
        start/end offsets into the normalised input text.

        Returns the client-facing result plus two private keys the route strips
        before replying: "_usage" (summed token usage) and "_chunks".
        """
        text = unicodedata.normalize("NFC", (text or "").strip())
        if not text:
            return {"errors": [], "corrected_text": "", "summary_si": "",
                    "summary_en": "", "pre_fixed_count": 0,
                    "stats": _stats(text, []), "_usage": None, "_chunks": 0}
        if self.client is None:
            raise RuntimeError(self.model_error or "Gemini model not ready")

        chunks = _split_chunks(text, int(self.cfg.get("chunk_words", 250) or 250))
        precheck = self.db.get_precheck_map()
        inject_block = self.db.export_for_injection(int(self.cfg.get("inject_top_n", 40)))

        offsets, pos = [], 0
        for c in chunks:
            offsets.append(pos)
            pos += len(c)

        def run(i):
            try:
                return self._proofread_chunk(chunks[i], offsets[i], precheck, inject_block), None
            except Exception as e:          # one bad chunk must not sink the rest
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

        errors, corrected_parts, usage = [], [], None
        pre_fixed_count, summaries = 0, []
        for chunk, (r, e) in zip(chunks, results):
            if r is None:
                corrected_parts.append(chunk)      # unchecked part stays as typed
                continue
            errors.extend(r["errors"])
            corrected_parts.append(r["corrected"])
            pre_fixed_count += r["pre_fixed"]
            summaries.append((r["summary_si"], r["summary_en"]))
            usage = _add_usage(usage, r["usage"])

        if len(chunks) == 1:
            summary_si, summary_en = summaries[0]
        else:
            summary_si = "වචන %d ක් කොටස් %d කින් පරීක්ෂා කළා — ගැටලු %d ක් හමු විය." % (
                len(text.split()), len(chunks), len(errors))
            summary_en = "Checked %d words in %d parts — %d issue(s) found." % (
                len(text.split()), len(chunks), len(errors))
        if failed:
            reason = getattr(failed[0], "message", None) or str(failed[0])
            summary_si += "  ⚠️ කොටස් %d ක් පරීක්ෂා කළ නොහැකි විය — නැවත උත්සාහ කරන්න." % len(failed)
            summary_en += "  ⚠️ %d of %d part(s) could not be checked (%s) — try again." % (
                len(failed), len(chunks), reason[:80])

        return {
            "errors": errors,
            "corrected_text": "".join(corrected_parts),
            "summary_si": summary_si,
            "summary_en": summary_en,
            "pre_fixed_count": pre_fixed_count,
            "parts": len(chunks),
            "parts_failed": len(failed),
            "stats": _stats(text, errors, pre_fixed_count),
            "_usage": usage,
            "_chunks": len(chunks),
        }

    def _proofread_chunk(self, chunk, offset, precheck, inject_block):
        """Check one chunk. `offset` = its position in the full input text."""
        lead = chunk[:len(chunk) - len(chunk.lstrip())]
        trail = chunk[len(chunk.rstrip()):]
        original = chunk.strip()
        base = offset + len(lead)               # where `original` starts in the input
        if not original:
            return {"errors": [], "corrected": chunk, "pre_fixed": 0,
                    "summary_si": "", "summary_en": "", "usage": None}

        # LAYER 1 — pre-check from the human corrections DB.
        work, pre_fixed = original, []
        for wrong, correct in precheck.items():
            if wrong and wrong in work:
                work = work.replace(wrong, correct)
                pre_fixed.append({
                    "original": wrong, "correction": correct, "type": "spelling",
                    "confidence": 1.0, "source": "human_db",
                    "explanation_si": "මිනිස් සමාලෝචකයෙකු විසින් නිවැරදි කළ දෝෂයකි",
                    "explanation_en": "Previously corrected by a human reviewer",
                })

        # LAYER 2 — inject top corrections + protect English.
        english = sorted(set(re.findall(r"[A-Za-z]+", work)))
        english_note = ""
        if english:
            english_note = ("\n\nCRITICAL: These English words appear in the text. "
                            "They are ALL valid. NEVER flag them: " + ", ".join(english))
        prompt = self.prompt + inject_block + english_note + "\n\nSinhala text to proofread:\n" + work

        # LAYER 3 — Gemini (plain HTTPS REST). Gemini's latency varies a lot
        # (thinking models especially), so a timeout / overload / rate-limit on
        # one part is retried once instead of failing the user's whole check.
        for attempt in range(PART_ATTEMPTS):
            try:
                with self.sem:
                    raw, usage = self.client.generate_content_ex(
                        prompt, temperature=0.05, json_mode=True)
                break
            except GeminiRestError as e:
                if attempt + 1 >= PART_ATTEMPTS or not _is_transient(e):
                    raise
                print("  part retry after: %s" % e.message[:80], flush=True)
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
        gemini_errors.sort(key=lambda x: x.get("confidence", 1), reverse=True)
        errors = pre_fixed + gemini_errors[:MAX_ERRORS_PER_CHUNK]

        # Positions in the ORIGINAL chunk (what the client displays), shifted to
        # whole-input offsets; then document order.
        _locate_all(original, errors, base)
        errors.sort(key=lambda x: (x["start"] is None, x["start"] or 0))

        corrected = str(data.get("corrected_text", work)) or work
        corrected = _restore_linebreaks(work, corrected)
        return {
            "errors": errors,
            "corrected": lead + corrected + trail,
            "pre_fixed": len(pre_fixed),
            "summary_si": str(data.get("summary_si", "")),
            "summary_en": str(data.get("summary_en", "")),
            "usage": usage,
        }

    def max_words(self):
        return int(self.cfg.get("max_words", 5000) or 5000)

    # ----- transcription (voice typing) ---------------------------------
    def transcribe(self, audio_bytes, mime="audio/wav"):
        """Returns (text, usage)."""
        if self.client is None:
            raise RuntimeError(self.model_error or "Gemini model not ready")
        with self.sem:
            return self.client.transcribe_audio_ex(audio_bytes, mime=mime)


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
    sent = {m.end() for m in re.finditer(r"[.!?෴]\s+", text)}
    chunks, i, start_pos = [], 0, 0
    while i < len(words):
        end_i = i + max_words
        if end_i >= len(words):
            chunks.append(text[start_pos:])
            break
        cut = None
        floor = i + max_words // 2        # never make a chunk smaller than half
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


def _locate_all(text, errors, base):
    """Set start/end (offset by `base`) for each error's `original` in `text`.
    Each error claims the next unclaimed occurrence, so repeats don't collide."""
    claimed = []
    for e in errors:
        word = e.get("original", "")
        e["start"] = e["end"] = None
        if not word:
            continue
        at = 0
        while True:
            idx = text.find(word, at)
            if idx == -1:
                break
            span = (idx, idx + len(word))
            if not any(span[0] < c[1] and span[1] > c[0] for c in claimed):
                claimed.append(span)
                e["start"], e["end"] = base + span[0], base + span[1]
                break
            at = idx + 1


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


# ----- client identity ---------------------------------------------------
# v5+ clients send who they are; older clients are known by IP only (the admin
# panel then falls back to a reverse-DNS computer name).
_CLIENT_PATHS = ("/status", "/proofread", "/transcribe", "/record_correction")


def _client_ip():
    return request.remote_addr or "?"


@app.before_request
def _identify_client():
    request._t0 = time.time()
    if request.path not in _CLIENT_PATHS:
        return
    h = request.headers
    host, user, ver = h.get("X-Client-Host", ""), h.get("X-Client-User", ""), h.get("X-Client-Version", "")
    heartbeat = request.path == "/status" and h.get("X-Heartbeat") == "1"
    if host or user or ver or heartbeat:
        try:
            STATE.usage.touch_client(_client_ip(), host, user, ver, heartbeat=heartbeat)
        except Exception as e:
            print("client identity not recorded:", e, flush=True)


# ----- live console log --------------------------------------------------
# Waitress (unlike Flask's dev server) does not print a line per request, so we
# print our own. This is what shows connected client IPs live in the console.
# Heartbeats (every open client app pings /status), static files and the admin
# dashboard's live polling are skipped so real traffic stays readable.
@app.after_request
def _log_request(resp):
    try:
        if (request.headers.get("X-Heartbeat") == "1"
                or request.path.startswith("/static/")
                or request.path.startswith("/admin/api/")):
            return resp
        ms = int((time.time() - getattr(request, "_t0", time.time())) * 1000)
        print("%s  %-15s %-4s %-18s %s  %sms" % (
            datetime.now().strftime("%H:%M:%S"),
            _client_ip(),
            request.method,
            request.path[:18],
            resp.status_code,
            ms,
        ), flush=True)          # flush: output may be redirected to a log file
    except Exception:
        pass
    return resp


@app.route("/status")
def status():
    return jsonify({
        "status": "online",
        "model": STATE.cfg.get("model"),
        "corrections_total": STATE.db.get_stats()["total"],
        "model_ready": STATE.client is not None,
        "version": API_VERSION,
        "server_name": STATE.cfg.server_name(),
        "max_words": STATE.max_words(),
        "chunk_words": int(STATE.cfg.get("chunk_words", 250) or 250),
        # so clients can wait long enough: parts run `parallel` at a time, each
        # part may take up to part_timeout x part_attempts seconds.
        "parallel": int(STATE.cfg.get("max_concurrent", 4) or 4),
        "part_timeout": int(STATE.cfg.get("request_timeout", 120) or 120),
        "part_attempts": PART_ATTEMPTS,
        "client_latest_version": STATE.cfg.get("client_latest_version", ""),
        "client_update_note": STATE.cfg.get("client_update_note", ""),
    })


@app.route("/proofread", methods=["POST"])
def proofread():
    t0 = time.time()
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    client_ip = _client_ip()
    words = len(text.split())
    if words > STATE.max_words():
        return jsonify({
            "error": "too_long", "max_words": STATE.max_words(), "words": words,
            "summary_si": "පාඨය දිග වැඩියි — වචන %d ක් (උපරිමය %d)." % (words, STATE.max_words()),
            "summary_en": "Text too long: %d words (limit %d). Split it into smaller parts."
                          % (words, STATE.max_words()),
        }), 413
    try:
        result = STATE.proofread(text)
        usage, chunks = result.pop("_usage", None), result.pop("_chunks", 1)
        latency = int((time.time() - t0) * 1000)
        STATE.usage.log(client_ip, "ok", result["stats"]["total_words"],
                        result["stats"]["errors_found"], result.get("pre_fixed_count", 0),
                        latency, chunks, usage)
        return jsonify(result)
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        STATE.usage.log(client_ip, "error", words, 0, 0, latency)
        msg = getattr(e, "message", None) or str(e)
        return jsonify({
            "errors": [], "corrected_text": text,
            "summary_si": "Proxy දෝෂයකි", "summary_en": "Proxy error: %s" % msg[:160],
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
    client_ip = _client_ip()
    if not audio_b64:
        return jsonify({"text": "", "error": "no audio"}), 400
    try:
        audio = base64.b64decode(audio_b64)
        text, usage = STATE.transcribe(audio, mime=mime)
        latency = int((time.time() - t0) * 1000)
        STATE.usage.log(client_ip, "voice", len(text.split()), 0, 0, latency, 1, usage)
        return jsonify({"text": text})
    except Exception as e:
        latency = int((time.time() - t0) * 1000)
        STATE.usage.log(client_ip, "voice_error", 0, 0, 0, latency)
        msg = getattr(e, "message", None) or str(e)
        return jsonify({"text": "", "error": msg[:200]}), 500


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
            added_by=_client_ip(), source="client_edit",
            precheck_threshold=int(STATE.cfg.get("precheck_threshold", 5)),
        )
        if res.get("status") in ("added", "updated"):
            saved += 1
    return jsonify({"status": "ok", "saved": saved,
                    "total": STATE.db.get_stats()["total"]})


def main():
    host = STATE.cfg.get("host", "0.0.0.0")
    port = int(STATE.cfg.get("port", 8765))
    # Every client request holds a thread while it waits for Gemini (long checks
    # for minutes). Too few threads and heartbeats queue behind them, so clients
    # wrongly show "offline": never run with fewer than 32.
    threads = max(32, int(STATE.cfg.get("waitress_threads", 32) or 32))
    print("=" * 50)
    print(" Sinhala Proofreader Proxy Server")
    print(" Model:", STATE.cfg.get("model"),
          "| Key:", "SET" if STATE.cfg.get_api_key() else "MISSING")
    print(" Server name:", STATE.cfg.server_name())
    print(" Corrections:", STATE.db.get_stats()["total"],
          "| Usage rows:", STATE.usage.row_count())
    print(" Listening on http://%s:%d   (admin: /admin)" % (host, port))
    if STATE.model_error:
        print(" WARNING:", STATE.model_error)

    try:
        from waitress import serve
    except ImportError:
        print(" WARNING: waitress not installed - falling back to Flask's dev")
        print("          server (not recommended for multiple LAN clients).")
        print("          Run INSTALL.bat, or:  pip install waitress")
        print("=" * 50)
        app.run(host=host, port=port, threaded=True)
        return

    print(" Server: waitress (production WSGI, %d threads)" % threads)
    print("=" * 50)
    serve(app, host=host, port=port, threads=threads)


if __name__ == "__main__":
    main()
