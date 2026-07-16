# -*- coding: utf-8 -*-
"""
gemini_rest.py — minimal Gemini client over plain HTTPS REST (no SDK).

Why this exists
---------------
The proxy used to call Gemini through the `google.generativeai` package. That
package is now DEPRECATED and, on recent Python builds (3.14), it produces a
confusing failure:

    404 POST .../v1beta/models/gemini-2.0-flash:generateContent?$alt=json;enum-enc

This module talks to the Generative Language REST API directly using `requests`
(already a dependency). It is firewall-friendly (plain HTTPS, no gRPC), works on
any Python 3.x, and gives clear error messages. It exposes exactly what the
proxy needs:

    * list_models()      -> [model ids that support generateContent]
    * generate_content() -> str (the model's text reply)
    * test()             -> (ok: bool, message: str)
"""

import requests

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 60

# Friendly ordering hint: flash/lite first (cheap, free-tier), then the rest.
_PREFERRED = ("flash", "lite", "pro")


class GeminiRestError(Exception):
    """A short, human-readable failure. `detail` carries raw API text."""

    def __init__(self, message, status=None, detail=""):
        super().__init__(message)
        self.message = message
        self.status = status
        self.detail = detail


class GeminiRest:
    def __init__(self, api_key, model="gemini-2.5-flash", timeout=DEFAULT_TIMEOUT):
        self.api_key = (api_key or "").strip()
        self.model = _short_name(model) or "gemini-2.5-flash"
        self.timeout = timeout

    # ----- models --------------------------------------------------------
    def list_models(self):
        """Return short model ids (no 'models/' prefix) that can generateContent."""
        if not self.api_key:
            raise GeminiRestError("No API key set")
        url = "%s/models?key=%s&pageSize=200" % (API_ROOT, self.api_key)
        # Keep this snappy — it runs when the admin dashboard loads.
        try:
            r = requests.get(url, timeout=min(self.timeout, 15))
        except requests.exceptions.RequestException as e:
            raise GeminiRestError("Network error: %s" % e, detail=str(e))
        if r.status_code != 200:
            raise _http_error(r)
        out = []
        for m in (r.json().get("models") or []):
            methods = m.get("supportedGenerationMethods") or []
            if "generateContent" in methods:
                name = _short_name(m.get("name", ""))
                if name:
                    out.append(name)
        return _order_models(set(out))

    # ----- generation ----------------------------------------------------
    def generate_content(self, prompt, temperature=0.05, json_mode=True):
        """Call <model>:generateContent and return the candidate text."""
        if not self.api_key:
            raise GeminiRestError("No API key set")
        url = "%s/models/%s:generateContent?key=%s" % (API_ROOT, self.model, self.api_key)
        gen_config = {"temperature": temperature}
        if json_mode:
            gen_config["responseMimeType"] = "application/json"
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": gen_config,
        }
        try:
            r = requests.post(url, json=body, timeout=self.timeout)
        except requests.exceptions.RequestException as e:
            raise GeminiRestError("Network error: %s" % e, detail=str(e))
        if r.status_code != 200:
            raise _http_error(r)
        return _extract_text(r.json())

    # ----- diagnostics ---------------------------------------------------
    def test(self):
        """Lightweight reachability/auth check. Returns (ok, message)."""
        try:
            self.generate_content("Reply with the single word OK.", json_mode=False)
            return True, "OK"
        except GeminiRestError as e:
            return False, e.message


# ----- helpers -----------------------------------------------------------
def _short_name(name):
    name = (name or "").strip()
    if name.startswith("models/"):
        name = name[len("models/"):]
    return name


def _order_models(names):
    """flash/lite/pro families first (alpha within), then everything else."""
    def rank(n):
        low = n.lower()
        for i, key in enumerate(_PREFERRED):
            if key in low:
                return (i, n)
        return (len(_PREFERRED), n)
    return sorted(names, key=rank)


def _extract_text(data):
    candidates = data.get("candidates") or []
    if not candidates:
        fb = data.get("promptFeedback", {}) or {}
        reason = fb.get("blockReason", "")
        raise GeminiRestError(
            "Empty response from model" + (" (blocked: %s)" % reason if reason else "")
        )
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not text:
        finish = candidates[0].get("finishReason", "")
        raise GeminiRestError(
            "Empty response from model" + (" (finishReason: %s)" % finish if finish else "")
        )
    return text


def _http_error(r):
    detail = ""
    try:
        detail = (r.json().get("error", {}) or {}).get("message", "") or ""
    except Exception:
        detail = (r.text or "")[:200]
    code = r.status_code
    if code == 404:
        # Google's own message is the most useful thing here — it usually says
        # e.g. "is not found for API version v1beta, or is not supported for
        # generateContent". Surface it verbatim.
        msg = "Model not found (HTTP 404): %s" % (detail[:200] or
              "pick another model from the dropdown and Save Settings")
    elif code in (401, 403):
        msg = "API key invalid or lacks access (HTTP %d): %s" % (code, detail[:120])
    elif code == 429:
        msg = "Rate/quota limit hit (HTTP 429) — wait or try a different model"
    elif code == 400:
        msg = "Bad request (HTTP 400): %s" % (detail[:140] or "check the API key")
    else:
        msg = "Gemini HTTP %d: %s" % (code, detail[:140])
    return GeminiRestError(msg, status=code, detail=detail)
