# Proofreader App Architecture

> Gemini-API-only. No offline dictionary / spell_checker / grammar_checker /
> sinmorph — those were removed. Two connection modes: **Direct** and **LAN Proxy**.

## Component map
```
main.py
└── gui/main_window.py (MainWindow)         window icon from assets/icon.(ico|png)
    ├── gui/settings_dialog.py              connection mode, key, model, theme, i18n
    ├── gui/welcome_dialog.py · widgets.py · theme.py · i18n.py
    └── engine/proofreader.py (orchestrator)
        ├── engine/gemini_engine.py         Direct mode — google-generativeai
        ├── engine/lan_proxy_engine.py      LAN mode — POST to Control PC
        └── engine/corrections_db.py        SQLite self-learning store

proxy_server/  (runs only on the Control PC; not packaged)
└── proxy.py (Flask)
    ├── gemini_rest.py                       Gemini over plain HTTPS REST
    ├── corrections_db.py                    identical copy of engine/corrections_db.py
    ├── admin_panel.py (/admin)              dashboard, model dropdown, corrections, usage
    ├── config_proxy.py · usage_logger.py
    └── templates/  +  *.bat helpers
```

## Connection modes
- **Direct** — `GeminiProofreader` calls Gemini from the client (key on the PC).
- **LAN Proxy** — `LanProxyProofreader` POSTs text to `http://<control-pc>:8765/proofread`;
  the Control PC holds the key and calls Gemini. Clients need no key, no internet.

The orchestrator never raises — API/network failures become a structured
`{"ok": False, "error_kind": ...}` result the GUI shows.

## Result / error object schema
```python
{
  "ok": True,
  "errors": [
    {
      "original": "ජිවිතය",
      "correction": "ජීවිතය",
      "type": "spelling",          # spelling | grammar | grammar_discord | encoding_error
      "explanation_si": "...",
      "explanation_en": "...",
      "confidence": 0.92,
      "start": 14, "end": 19        # char offsets in the text (None if not locatable)
    }
  ],
  "corrected_text": "...",
  "summary_si": "...", "summary_en": "...",
  "pre_fixed_count": 0,
  "stats": {"total_words": .., "errors_found": .., "spell_errors": .., ...}
}
```

## Proofreading pipeline (3 layers — same on client Direct + proxy)
1. **Pre-check** — apply confirmed human corrections from the DB locally,
   instantly, at confidence 1.0 (no API call).
2. **Inject** — add the top human-verified corrections to the prompt as few-shot
   examples; also list any English words present so Gemini never flags them.
3. **Gemini** — one `generateContent` call, `temperature≈0.05`,
   `responseMimeType=application/json`. Parse tolerantly (strip ``` fences),
   drop flags below confidence 0.75, cap at 10 errors.

## Self-learning corrections (CorrectionsDB, SQLite)
- A reviewer edits the corrected text and saves → word-level diffs recorded.
- New entries start in **inject_only**; after a correction is **confirmed** and
  seen ≥ `precheck_threshold` times it is promoted to **precheck** (instant local fix).
- Identical class on client and proxy; `self.data` exposes the legacy dict shape
  for the `/corrections` sync endpoint. LAN clients mirror the proxy store via
  `load_from_dict(...)`.

## Admin panel (Control PC)
`http://localhost:8765/admin` — dashboard with a **model dropdown** (populated from
the key's real models via `list_models()`), Save-Settings model verification,
auto-heal off retired models, corrections moderation, usage log, key + config.

## Key gotchas
- Sinhala chars are multi-byte in UTF-8 — use character positions, normalize NFC.
- tkinter Text positions are `"line.char"`, not absolute indexes.
- The window/EXE icon needs a `_resource_path()` that honors `sys._MEIPASS` when frozen.
- Default model `gemini-2.5-flash`; `gemini-2.0-flash` is retired for new keys.
