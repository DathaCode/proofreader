# -*- coding: utf-8 -*-
"""
Offline tests for the v5 LAN-proxy features (no network, no API key).

Covers: proxy long-text chunking + parallel checks (fake Gemini), the SQLite
usage store (clients, filters, cost, two-Control-PC merge), client highlight
spans, the fast editor's segmentation, local history, and i18n templates.

Run:  python tests/test_v5.py     (PYTHONUTF8=1 recommended on Windows)
"""

import os
import re
import sys
import json
import time
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROXY = os.path.join(ROOT, "proxy_server")
sys.path.insert(0, ROOT)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TMP = tempfile.mkdtemp(prefix="sp_v5_")

# The proxy reads its paths at import time: point them at a temp folder first.
sys.path.insert(0, PROXY)
import config_proxy  # noqa: E402
config_proxy.CONFIG_PATH = os.path.join(TMP, "proxy_config.json")
config_proxy.CORRECTIONS_PATH = os.path.join(TMP, "corrections.db")
config_proxy.USAGE_DB_PATH = os.path.join(TMP, "usage.db")
config_proxy.LOG_PATH = os.path.join(TMP, "usage_log.csv")
config_proxy.API_KEY_PATH = os.path.join(TMP, "api_key.txt")
import proxy  # noqa: E402
from usage_store import UsageStore, cost_of, price_for  # noqa: E402

_PASS = _FAIL = 0


def check(name, cond):
    global _PASS, _FAIL
    if cond:
        _PASS += 1; print("  PASS  " + name)
    else:
        _FAIL += 1; print("  FAIL  " + name)


class FakeGemini:
    """Flags every word containing 'x' as a spelling error."""
    calls = 0
    lock = threading.Lock()

    def generate_content_ex(self, prompt, temperature=0.05, json_mode=True):
        body = prompt.split("Sinhala text to proofread:\n", 1)[1]
        with self.lock:
            FakeGemini.calls += 1
        time.sleep(0.2)
        errs = [{"original": w, "correction": w.replace("x", "X"), "type": "spelling",
                 "confidence": 0.95, "explanation_si": "", "explanation_en": ""}
                for w in sorted(set(re.findall(r"\S*x\S*", body)))]
        return (json.dumps({"errors": errs, "corrected_text": body.replace("x", "X"),
                            "summary_si": "", "summary_en": ""}),
                {"model": "gemini-2.5-flash", "in": 1000, "audio": 0, "out": 100})


def test_chunking():
    split = proxy._split_chunks
    para = lambda n, t: " ".join("ව%s%d" % (t, i) for i in range(n)) + "."
    text = "\n\n".join(para(120, chr(97 + k)) for k in range(10))
    parts = split(text, 250)
    check("chunks rejoin to the exact original", "".join(parts) == text)
    check("chunks stay within the word budget", all(len(p.split()) <= 250 for p in parts))
    check("chunks cut at paragraph breaks", all(p.rstrip().endswith(".") for p in parts[:-1]))
    flat = " ".join("w%d" % i for i in range(700))
    check("text without breaks still splits losslessly", "".join(split(flat, 250)) == flat)
    check("short text is one chunk", split("එක දෙක", 250) == ["එක දෙක"])

    S = proxy.STATE
    S.client, S.model_error = FakeGemini(), ""
    S.cfg.set("max_concurrent", 4)
    paras = [para(100, chr(97 + k)) for k in range(12)]
    paras[2] = paras[2].replace("වc5 ", "වx5 ")
    paras[9] = paras[9].replace("වj7 ", "වx5 ")          # same typo again, later part
    long_text = "\n\n".join(paras)
    FakeGemini.calls = 0
    t0 = time.time()
    res = S.proofread(long_text)
    dt = time.time() - t0
    check("long text split into parallel parts", res["_chunks"] >= 5 and FakeGemini.calls == res["_chunks"])
    check("parts run in parallel", dt < 0.2 * res["_chunks"] * 0.75)
    check("repeated typo found in both parts", len(res["errors"]) == 2)
    check("error offsets point at the right words",
          all(long_text[e["start"]:e["end"]] == e["original"] for e in res["errors"]))
    check("corrected text keeps paragraphs", res["corrected_text"].count("\n\n") == 11)
    check("token usage summed over parts", res["_usage"]["in"] == 1000 * res["_chunks"])

    # A transient Gemini failure (overload / timeout) on a part is retried once.
    from gemini_rest import GeminiRestError
    real = FakeGemini.generate_content_ex
    state = {"n": 0}

    def flaky(self, prompt, **kw):
        state["n"] += 1
        if state["n"] == 1:
            raise GeminiRestError("overloaded", status=503)
        return real(self, prompt, **kw)
    FakeGemini.generate_content_ex = flaky
    sleep, proxy.time.sleep = proxy.time.sleep, lambda s: None
    r = S.proofread("මම පාසල් යමි.")
    check("transient 503 on a part is retried and succeeds", state["n"] == 2 and r["_chunks"] == 1)

    def bad_request(self, prompt, **kw):
        state["n"] += 1
        raise GeminiRestError("bad request", status=400)
    FakeGemini.generate_content_ex = bad_request
    state["n"] = 0
    try:
        S.proofread("මම පාසල් යමි.")
        check("non-transient error is not retried", False)
    except GeminiRestError:
        check("non-transient error is not retried", state["n"] == 1)
    FakeGemini.generate_content_ex = real
    proxy.time.sleep = sleep

    c = proxy.app.test_client()
    st = c.get("/status").get_json()
    check("/status tells clients the timing (parallel, part timeout, retries)",
          st["parallel"] == 4 and st["part_timeout"] >= 120 and st["part_attempts"] == 2)
    S.cfg.set("max_words", 500)
    r = c.post("/proofread", json={"text": long_text})
    check("over the word limit -> HTTP 413", r.status_code == 413)
    S.cfg.set("max_words", 5000)
    r = c.post("/proofread", json={"text": long_text}, headers={"X-Client-Host": "DESK-1"})
    check("/proofread 200 without private keys", r.status_code == 200 and "_usage" not in r.get_json())
    cl = S.usage.client("127.0.0.1")
    check("client identity recorded from headers", cl and cl["hostname"] == "DESK-1")
    n = S.usage.row_count()
    c.get("/status", headers={"X-Heartbeat": "1"})
    check("heartbeat is not logged as usage", S.usage.row_count() == n)


def test_usage_store():
    d = tempfile.mkdtemp(dir=TMP)
    pricing = config_proxy.DEFAULT_PRICING
    check("price: longest prefix wins", price_for("gemini-2.5-flash-lite-x", pricing)["in"] == 0.10)
    check("cost: 2.5-pro 3000 in / 1600 out = $0.01975",
          abs(cost_of({"model": "gemini-2.5-pro", "in": 3000, "audio": 0, "out": 1600}, pricing) - 0.01975) < 1e-9)
    legacy = os.path.join(d, "usage_log.csv")
    with open(legacy, "w", encoding="utf-8") as f:
        f.write("timestamp,client_ip,words,errors_found,pre_fixed,latency_ms,status\n")
        for i in range(50):
            f.write("2026-09-%02dT10:00:00.%06d,10.1.2.%d,60,1,0,%d,ok\n" % (1 + i % 28, i, 170 + i % 2, 3000 + i))
    A = UsageStore(os.path.join(d, "a.db"), lambda: "PC-246", lambda: pricing, legacy_csv=legacy)
    B = UsageStore(os.path.join(d, "b.db"), lambda: "PC-102", lambda: pricing, legacy_csv=legacy)
    check("legacy CSV migrated once", A.row_count() == 50)
    for i in range(3):
        B.log("10.1.2.171", "ok", 80, 1, 0, 2000 + i, 1, {"model": "gemini-2.5-flash", "in": 900, "audio": 0, "out": 90})
    added, skipped = A.import_csv(B.export_csv(), "PC-102")
    check("merge imports only new rows (shared history deduped)", (added, skipped) == (3, 50))
    check("re-import is a no-op", A.import_csv("﻿﻿" + B.export_csv(), "PC-102") == (0, 53))
    A.rename_client("10.1.2.170", "Kamal")
    check("rename + filter by client", A.query_logs({"client": "10.1.2.170"})[0][0]["client_name"] == "Kamal")
    check("month filter", A.totals({"month": "2026-09"})["requests"] == 50)
    check("relabel copied history", A.relabel("PC-246", "PC-102", "2026-09-30") == 50)


def test_client_side():
    from gui.main_window import _visual_span
    t = "ලන්කාවේ අද්‍යාපන"
    check("highlight never splits a vowel sign", _visual_span(t, 0, 6) == (0, 7))
    i = t.index("අද්")
    check("highlight keeps ZWJ conjuncts whole", t[slice(*_visual_span(t, i, i + 3))] == "අද්‍යා")

    from engine.lan_proxy_engine import timeout_for
    check("client timeout scales with length", timeout_for(80) == 150 and timeout_for(5000) == 510)

    from gui.history import History
    h = History(path=os.path.join(TMP, "history.json"), max_items=3)
    for k in range(5):
        h.add("text %d" % k, "fixed %d" % k, 2, k)
    h.add("text 4", "fixed 4b", 2, 0)
    h2 = History(path=os.path.join(TMP, "history.json"))
    check("history: newest first, capped, deduped, persisted",
          [x["original"] for x in h2.items] == ["text 4", "text 3", "text 2"])

    from gui.i18n import STRINGS
    spec = lambda s: re.findall(r"%[-0-9.]*[sdf]", s or "")
    bad = [k for k, v in STRINGS.items() if spec(v.get("en")) != spec(v.get("si"))]
    check("every Sinhala template takes the same values as English", not bad)

    import tkinter as tk
    from gui.widgets import segment_text
    try:
        root = tk.Tk(); root.withdraw()
    except tk.TclError:
        print("  SKIP  editor segmentation (no display)")
        return
    txt = tk.Text(root)
    body = " ".join(["ලංකාවේ"] * 50) + "\n" + "එක"
    txt.insert("1.0", body)
    segment_text(txt)
    check("segmentation leaves the text unchanged", txt.get("1.0", "end-1c") == body)
    check("segmentation tags long lines only", bool(txt.tag_ranges("_seg0")) and
          not any(str(r).startswith("2.") for r in txt.tag_ranges("_seg0")))

    from gui.widgets import clipboard_text, SinhalaText
    big = " ".join(["ලංකාවේ", "අධ්‍යාපනය", "ගැන"] * 1000)    # > 4 KB of UTF-8
    root.clipboard_clear(); root.clipboard_append(big); root.update()
    check("long Sinhala clipboard text is not corrupted", clipboard_text(root) == big)
    view = SinhalaText(root)
    view.insert_text("1.0", "ABC DEF")
    view.insert_text("1.3", " " + big)
    check("segmented insert keeps text exact", view.text.get("1.0", "end-1c") == "ABC " + big + " DEF")
    root.destroy()


def run():
    print("== proxy chunking"); test_chunking()
    print("== usage store"); test_usage_store()
    print("== client"); test_client_side()
    print("\n%d passed, %d failed" % (_PASS, _FAIL))
    return _FAIL == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
