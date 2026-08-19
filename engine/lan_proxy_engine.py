# -*- coding: utf-8 -*-
"""
LanProxyProofreader — client-side engine for LAN deployment.

Sends text to the Control PC proxy instead of calling Gemini directly, so the
client machine needs NO API key and NO internet (only LAN access to the proxy).
Returns a dict in the same shape the GUI expects (ok / mode / original / errors
with start-end / corrected_text / summary / stats).
"""

import unicodedata

import requests as req_lib

from .gemini_engine import GeminiError, _restore_linebreaks


class LanProxyProofreader:
    def __init__(self, proxy_url):
        self.proxy_url = (proxy_url or "").rstrip("/")

    # ----- diagnostics ---------------------------------------------------
    def test_connection(self):
        try:
            r = req_lib.get(self.proxy_url + "/status", timeout=5)
            if r.status_code == 200:
                data = r.json()
                model = data.get("model", "")
                corr = data.get("corrections_total", 0)
                return (True, "සාර්ථකයි! Proxy online | %s | Corrections: %s"
                        % (model, corr))
            return (False, "Proxy error: HTTP %d" % r.status_code)
        except req_lib.exceptions.ConnectionError:
            return (False, "Control PC සම්බන්ධ නොවේ — IP/Port හෝ Firewall පරීක්ෂා කරන්න "
                           "(Cannot reach Control PC — check the LAN IP, port 8765, "
                           "and run FIREWALL_SETUP.bat as admin on the Control PC)")
        except req_lib.exceptions.Timeout:
            return (False, "Connection timed out — Control PC online ද? (firewall blocking 8765?)")
        except Exception as e:
            return (False, str(e)[:100])

    # ----- proofreading --------------------------------------------------
    def proofread(self, text, corrections_db=None, on_progress=None):
        text = unicodedata.normalize("NFC", (text or "").strip())
        if not text:
            return self._empty(text)
        if on_progress:
            on_progress("Control PC සමඟ පරීක්ෂා කරමින්...")

        # corrections_db is handled server-side in LAN mode; the client just
        # sends raw text to the proxy.
        try:
            r = req_lib.post(
                self.proxy_url + "/proofread",
                json={"text": text},
                timeout=60,
                headers={"Content-Type": "application/json"},
            )
        except req_lib.exceptions.ConnectionError:
            raise GeminiError(
                "Control PC proxy සම්බන්ධ නොවේ. Settings → Proxy URL නිවැරදිද?",
                "Cannot reach the Control PC proxy — check Settings → Proxy URL",
                kind="network",
            )
        except req_lib.exceptions.Timeout:
            raise GeminiError(
                "ප්‍රතිචාරය ප්‍රමාද විය (60s). Control PC online ද? Text කෙටි කරන්න.",
                "Proxy timed out (60s) — is the Control PC online? Try shorter text.",
                kind="timeout",
            )
        except Exception as e:
            raise GeminiError("Proxy දෝෂයකි", "Proxy error: %s" % e, kind="error")

        if r.status_code != 200:
            raise GeminiError(
                "Proxy දෝෂයකි (HTTP %d)" % r.status_code,
                "Proxy returned HTTP %d" % r.status_code,
                kind="error",
            )

        result = r.json()

        # Normalize schema: accept "errors" or "corrections".
        errors = result.get("errors")
        if errors is None:
            errors = result.get("corrections")
        errors = errors or []
        errors = [e for e in errors if float(e.get("confidence", 1)) >= 0.75]
        errors.sort(key=lambda x: x.get("confidence", 1), reverse=True)
        errors = errors[:10]

        corrected = result.get("corrected_text", text)
        # Keep the input's line-break layout even if the proxy returned a paragraph
        # (works even against an un-updated proxy).
        corrected = _restore_linebreaks(text, corrected)
        # Resolve highlight positions against the ORIGINAL text (what the Results
        # panel shows) — NOT the corrected text, where the wrong word is gone.
        # Pick each error's next unclaimed occurrence so repeated words don't all
        # land on the same span.
        claimed = []

        def _locate(word):
            if not word:
                return None, None
            start_at = 0
            while True:
                idx = text.find(word, start_at)
                if idx == -1:
                    return None, None
                span = (idx, idx + len(word))
                if not any(span[0] < c[1] and span[1] > c[0] for c in claimed):
                    claimed.append(span)
                    return span
                start_at = idx + 1

        for e in errors:
            e.setdefault("type", "spelling")
            e["start"], e["end"] = _locate(e.get("original", ""))

        stats = result.get("stats") or {}
        stats.setdefault("total_words", len(text.split()))
        stats.setdefault("errors_found", len(errors))
        stats.setdefault("spell_errors", sum(1 for e in errors if e.get("type") == "spelling"))
        stats.setdefault("grammar_errors", sum(1 for e in errors if e.get("type") in ("grammar", "grammar_discord")))
        stats.setdefault("encoding_errors", sum(1 for e in errors if e.get("type") == "encoding_error"))

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
                             json={"audio": b64, "mime": "audio/wav"}, timeout=90)
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
