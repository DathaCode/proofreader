# -*- coding: utf-8 -*-
"""
proofreader.py — orchestrator.

Connection modes (chosen in Settings):
  * "direct"     — call the Gemini API from this PC (needs a key)
  * "lan_proxy"  — send text to the Control PC proxy over the LAN (no key here)

A shared self-learning CorrectionsDB is loaded and passed to the engine. The
orchestrator never raises — API/network failures become a structured ok=False
result the GUI shows.
"""

import os
import unicodedata

from config import CONFIG_DIR
from .corrections_db import CorrectionsDB
from .gemini_engine import GeminiProofreader, GeminiError


def _normalize(text):
    return unicodedata.normalize("NFC", text or "")


# Live corrections DB stored in a writable, persistent location (survives .exe
# updates), NOT inside the read-only PyInstaller bundle.
CORRECTIONS_PATH = os.path.join(CONFIG_DIR, "corrections.db")


class SinhalaProofreader:
    def __init__(self, config):
        self.config = config
        self.corrections_db = CorrectionsDB(CORRECTIONS_PATH)
        self.engine = None
        self.mode = "direct"
        self._engine_sig = None
        self._refresh_engine()

    # ----- engine selection ---------------------------------------------
    def _refresh_engine(self):
        """(Re)build the active engine from current config if needed."""
        mode = self.config.get("connection_mode", "direct")
        if mode == "lan_proxy":
            url = self.config.get("proxy_url", "http://192.168.1.100:8765")
            sig = ("lan_proxy", url)
            if self._engine_sig != sig:
                from .lan_proxy_engine import LanProxyProofreader
                self.engine = LanProxyProofreader(url)
                self._engine_sig = sig
            self.mode = "lan_proxy"
        else:  # direct
            key = self.config.resolve_api_key()
            model = self.config.get("gemini_model", "gemini-2.5-flash")
            transport = self.config.get_transport()
            sig = ("direct", key, model, transport)
            if self._engine_sig != sig:
                self.engine = GeminiProofreader(key, model, transport=transport)
                self._engine_sig = sig
            self.mode = "direct"

    def rebuild_engine(self):
        """Call after settings change (mode / key / model / proxy URL)."""
        self._refresh_engine()

    # ----- public API ----------------------------------------------------
    def proofread(self, text, on_progress=None):
        text = _normalize(text)
        if not text.strip():
            return self._empty_result()

        self._refresh_engine()

        if self.mode == "direct" and not self.config.has_api_key():
            return self._error_result(
                text,
                "Gemini API Key එකක් අවශ්‍යයි. Settings → API Key එකතු කරන්න.",
                "A Gemini API key is required. Open Settings → API Key.",
                kind="no_key",
            )

        try:
            return self.engine.proofread(
                text, corrections_db=self.corrections_db, on_progress=on_progress
            )
        except GeminiError as exc:
            if on_progress:
                on_progress(exc.message_si)
            return self._error_result(
                text, exc.message_si, exc.message_en, kind=exc.kind, detail=exc.detail
            )
        except Exception as exc:  # final safety net — never crash the GUI
            return self._error_result(
                text, "අනපේක්ෂිත දෝෂයකි", "Unexpected error: %s" % str(exc)[:160],
                kind="error",
            )

    def transcribe(self, audio_path, on_progress=None):
        """Voice typing: WAV file -> Sinhala text (Gemini direct, or via proxy).

        Raises GeminiError on failure (the GUI catches and shows a message).
        """
        self._refresh_engine()
        if self.mode == "direct" and not self.config.has_api_key():
            raise GeminiError(
                "Gemini API Key එකක් අවශ්‍යයි. Settings → API Key එකතු කරන්න.",
                "A Gemini API key is required. Open Settings → API Key.",
                kind="no_key",
            )
        return self.engine.transcribe(audio_path, on_progress=on_progress)

    def test_connection(self):
        self._refresh_engine()
        try:
            return self.engine.test_connection()
        except GeminiError as exc:
            return False, exc.message_si + "  /  " + exc.message_en

    def sync_corrections_from_proxy(self):
        """Pull the corrections DB from the Control PC on startup (LAN mode)."""
        if self.mode != "lan_proxy":
            return
        try:
            import requests
            proxy_url = self.engine.proxy_url
            r = requests.get(proxy_url + "/corrections", timeout=5)
            if r.status_code == 200:
                # Mirror the proxy's authoritative store into our local SQLite
                # DB (in place — no file surgery, no connection churn).
                self.corrections_db.load_from_dict(r.json())
        except Exception as e:
            # Non-fatal: proxy may be offline; keep the local cache.
            print("Corrections sync skipped:", e)

    # ----- result builders ----------------------------------------------
    @staticmethod
    def _stats(text, errors):
        return {
            "total_words": len(text.split()),
            "errors_found": len(errors),
            "spell_errors": sum(1 for e in errors if e.get("type") == "spelling"),
            "grammar_errors": sum(
                1 for e in errors if e.get("type") in ("grammar", "grammar_discord")
            ),
            "encoding_errors": sum(
                1 for e in errors if e.get("type") == "encoding_error"
            ),
            "pre_fixed": 0,
        }

    def _empty_result(self):
        return {
            "mode": self.mode, "ok": True, "message": "",
            "error_found": False, "errors": [], "corrected_text": "",
            "original": "", "original_text": "", "pre_fixed_count": 0,
            "summary_si": "", "summary_en": "",
            "stats": self._stats("", []),
        }

    def _error_result(self, text, message_si, message_en, kind="error", detail=""):
        return {
            "mode": self.mode, "ok": False, "error_kind": kind,
            "error_detail": detail, "message": message_en,
            "error_found": False, "errors": [], "corrected_text": text,
            "original": text, "original_text": text, "pre_fixed_count": 0,
            "summary_si": "⚠️ " + message_si, "summary_en": "⚠️ " + message_en,
            "stats": self._stats(text, []),
        }
