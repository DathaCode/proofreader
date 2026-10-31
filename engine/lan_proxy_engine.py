# -*- coding: utf-8 -*-
"""
LanProxyProofreader — client-side engine for LAN deployment.

Sends text to the Control PC proxy instead of calling Gemini directly, so the
client machine needs NO API key and NO internet (only LAN access to the proxy).
Returns a dict in the same shape the GUI expects (ok / mode / original / errors
with start-end / corrected_text / summary / stats).

v5: every request identifies this PC (computer name, Windows user, app version)
so the admin panel can name and track clients; long texts are split and checked
in parallel by the proxy, so the timeout scales with the text length.
"""

import math
import socket
import getpass
import unicodedata

import requests as req_lib

from .gemini_engine import GeminiError, _restore_linebreaks

try:
    from version import __version__ as APP_VERSION
except Exception:  # pragma: no cover
    APP_VERSION = ""

DEFAULT_MAX_WORDS = 5000          # used until the proxy tells us its limit
CONFIDENCE_MIN = 0.75


def client_headers(heartbeat=False):
    """Identity headers sent with every request to the proxy."""
    try:
        host = socket.gethostname()
    except Exception:
        host = ""
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    h = {"X-Client-Host": host[:80], "X-Client-User": user[:80],
         "X-Client-Version": APP_VERSION}
    if heartbeat:
        h["X-Heartbeat"] = "1"
    return h


def timeout_for(words, chunk_words=250, parallel=4, part_seconds=90):
    """Seconds to wait for a check. The proxy checks ~chunk_words-word parts,
    `parallel` at a time; each wave of parts can take up to `part_seconds`
    (the proxy's per-call timeout x retries, learned from /status)."""
    parts = max(1, math.ceil(max(1, words) / float(chunk_words or 250)))
    waves = math.ceil(parts / float(max(1, parallel)))
    return int(min(1800, 60 + part_seconds * waves))


class LanProxyProofreader:
    def __init__(self, proxy_url):
        self.proxy_url = (proxy_url or "").rstrip("/")
        self.max_words = DEFAULT_MAX_WORDS
        self.chunk_words = 250
        self.parallel = 4
        self.part_seconds = 90
        self.server_info = {}

    # ----- diagnostics ---------------------------------------------------
    def status(self, heartbeat=False, timeout=5):
        """GET /status. Returns the proxy's info dict (raises on failure).
        Also learns the proxy's word limit. heartbeat=True marks this PC online."""
        r = req_lib.get(self.proxy_url + "/status", timeout=timeout,
                        headers=client_headers(heartbeat))
        r.raise_for_status()
        data = r.json()
        self.server_info = data
        self.max_words = int(data.get("max_words") or DEFAULT_MAX_WORDS)
        self.chunk_words = int(data.get("chunk_words") or 250)
        self.parallel = int(data.get("parallel") or 4)
        if data.get("part_timeout"):
            self.part_seconds = (int(data["part_timeout"]) * int(data.get("part_attempts") or 1)
                                 + 10 * int(data.get("part_attempts") or 1))
        return data

    def test_connection(self):
        try:
            data = self.status()
            model = data.get("model", "")
            corr = data.get("corrections_total", 0)
            name = data.get("server_name", "")
            return (True, "සාර්ථකයි! Proxy online%s | %s | Corrections: %s"
                    % ((" (%s)" % name) if name else "", model, corr))
        except req_lib.exceptions.ConnectionError:
            return (False, "Control PC සම්බන්ධ නොවේ — IP/Port හෝ Firewall පරීක්ෂා කරන්න "
                           "(Cannot reach Control PC — check the LAN IP, port 8765, "
                           "and run FIREWALL_SETUP.bat as admin on the Control PC)")
        except req_lib.exceptions.Timeout:
            return (False, "Connection timed out — Control PC online ද? (firewall blocking 8765?)")
        except req_lib.exceptions.HTTPError as e:
            return (False, "Proxy error: HTTP %s" % getattr(e.response, "status_code", "?"))
        except Exception as e:
            return (False, str(e)[:100])

    # ----- proofreading --------------------------------------------------
    def proofread(self, text, corrections_db=None, on_progress=None):
        text = unicodedata.normalize("NFC", (text or "").strip())
        if not text:
            return self._empty(text)
        words = len(text.split())
        if words > self.max_words:
            raise GeminiError(
                "පාඨය දිග වැඩියි — වචන %d ක් (උපරිමය %d). කොටස් කර පරීක්ෂා කරන්න." % (words, self.max_words),
                "Text too long: %d words (limit %d). Check it in smaller parts." % (words, self.max_words),
                kind="too_long",
            )
        if on_progress:
            on_progress("Control PC සමඟ පරීක්ෂා කරමින්...")

        timeout = timeout_for(words, self.chunk_words, self.parallel, self.part_seconds)
        # corrections_db is handled server-side in LAN mode; the client just
        # sends raw text to the proxy.
        try:
            r = req_lib.post(
                self.proxy_url + "/proofread",
                json={"text": text},
                timeout=timeout,
                headers=dict(client_headers(), **{"Content-Type": "application/json"}),
            )
        except req_lib.exceptions.ConnectionError:
            raise GeminiError(
                "Control PC proxy සම්බන්ධ නොවේ. Settings → Proxy URL නිවැරදිද?",
                "Cannot reach the Control PC proxy — check Settings → Proxy URL",
                kind="network",
            )
        except req_lib.exceptions.Timeout:
            raise GeminiError(
                "ප්‍රතිචාරය ප්‍රමාද විය (%ds). Control PC online ද?" % timeout,
                "Proxy timed out (%ds) — is the Control PC online?" % timeout,
                kind="timeout",
            )
        except Exception as e:
            raise GeminiError("Proxy දෝෂයකි", "Proxy error: %s" % e, kind="error")

        if r.status_code == 413:
            try:
                d = r.json()
            except Exception:
                d = {}
            self.max_words = int(d.get("max_words") or self.max_words)
            raise GeminiError(d.get("summary_si") or "පාඨය දිග වැඩියි",
                              d.get("summary_en") or "Text too long", kind="too_long")
        if r.status_code != 200:
            detail = ""
            try:
                detail = r.json().get("summary_en", "")
            except Exception:
                pass
            raise GeminiError(
                "Proxy දෝෂයකි (HTTP %d)" % r.status_code,
                detail or ("Proxy returned HTTP %d" % r.status_code),
                kind="error",
            )

        result = r.json()

        # Normalize schema: accept "errors" or "corrections".
        errors = result.get("errors")
        if errors is None:
            errors = result.get("corrections")
        errors = [e for e in (errors or []) if float(e.get("confidence", 1)) >= CONFIDENCE_MIN]

        corrected = result.get("corrected_text", text)
        # Keep the input's line-break layout even if the proxy returned a paragraph
        # (works even against an un-updated proxy).
        corrected = _restore_linebreaks(text, corrected)

        # Positions: a v5 proxy sends start/end into the text we sent — trust them
        # when they match. Otherwise (older proxy) locate each error ourselves:
        # the next unclaimed occurrence, so repeated words don't collide.
        claimed = []

        def _overlaps(span):
            return any(span[0] < c[1] and span[1] > c[0] for c in claimed)

        def _locate(word):
            if not word:
                return None, None
            start_at = 0
            while True:
                idx = text.find(word, start_at)
                if idx == -1:
                    return None, None
                span = (idx, idx + len(word))
                if not _overlaps(span):
                    claimed.append(span)
                    return span
                start_at = idx + 1

        for e in errors:
            e.setdefault("type", "spelling")
            s, en, word = e.get("start"), e.get("end"), e.get("original", "")
            if (isinstance(s, int) and isinstance(en, int) and 0 <= s < en <= len(text)
                    and text[s:en] == word and not _overlaps((s, en))):
                claimed.append((s, en))
            else:
                e["start"], e["end"] = _locate(word)
        errors.sort(key=lambda x: (x.get("start") is None, x.get("start") or 0))

        stats = result.get("stats") or {}
        stats.setdefault("total_words", words)
        stats["errors_found"] = len(errors)
        stats["spell_errors"] = sum(1 for e in errors if e.get("type") == "spelling")
        stats["grammar_errors"] = sum(1 for e in errors if e.get("type") in ("grammar", "grammar_discord"))
        stats["encoding_errors"] = sum(1 for e in errors if e.get("type") == "encoding_error")

        return {
            "mode": "lan_proxy",
            "ok": True,
            "message": "LAN Proxy",
            "error_found": len(errors) > 0,
            "errors": errors,
            "corrected_text": corrected,
            "original": text,
            "original_text": text,
            "pre_fixed_count": result.get("pre_fixed_count", 0),
            "parts": result.get("parts", 1),
            "parts_failed": result.get("parts_failed", 0),
            "summary_si": result.get("summary_si", ""),
            "summary_en": result.get("summary_en", ""),
            "stats": stats,
        }

    def transcribe(self, audio_path, on_progress=None):
        """Voice typing: send a WAV file to the proxy, get back Sinhala text."""
        import base64
        if on_progress:
            on_progress("Control PC හඬ පෙළට හරවමින්...")
        with open(audio_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        try:
            r = req_lib.post(self.proxy_url + "/transcribe",
                             json={"audio": b64, "mime": "audio/wav"}, timeout=90,
                             headers=client_headers())
        except req_lib.exceptions.ConnectionError:
            raise GeminiError("Control PC proxy සම්බන්ධ නොවේ.",
                              "Cannot reach the Control PC proxy", kind="network")
        except req_lib.exceptions.Timeout:
            raise GeminiError("හඬ පෙළට හැරවීම ප්‍රමාද විය.",
                              "Voice transcription timed out", kind="timeout")
        if r.status_code != 200:
            detail = ""
            try:
                detail = r.json().get("error", "")
            except Exception:
                pass
            raise GeminiError("හඬ පෙළට හැරවීම අසාර්ථකයි",
                              "Transcription failed: %s" % (detail or ("HTTP %d" % r.status_code)),
                              kind="error")
        return (r.json().get("text", "") or "").strip()

    def send_corrections(self, corrections):
        """Send human corrections to the proxy for central storage."""
        try:
            r = req_lib.post(
                self.proxy_url + "/record_correction",
                json={"corrections": corrections},
                timeout=10,
                headers=client_headers(),
            )
            return r.json()
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ----- helpers -------------------------------------------------------
    @staticmethod
    def _empty(text):
        return {
            "mode": "lan_proxy", "ok": True, "message": "LAN Proxy",
            "error_found": False, "errors": [], "corrected_text": "",
            "original": "", "original_text": "", "pre_fixed_count": 0,
            "summary_si": "", "summary_en": "",
            "stats": {"total_words": 0, "errors_found": 0, "spell_errors": 0,
                      "grammar_errors": 0, "encoding_errors": 0},
        }
