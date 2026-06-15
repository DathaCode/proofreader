# Sinhala Proofreader

A Windows desktop app that proofreads Sinhala text — catching spelling, grammar,
and Unicode/encoding errors — using the Google Gemini API. It ships as a single
self-contained `.exe`, has a modern dark/light UI with English ↔ Sinhala
switching, and gets smarter over time through a self-learning corrections
database.

Built for LAN deployment: up to ~20 client PCs can run fully offline, sending
their text to a single internet-connected **Control PC** that holds the API key
and does the Gemini calls on their behalf.

**Version:** 4.3.0 · **Platform:** Windows 10/11 64-bit · **Python:** 3.9+ (3.14 OK)

---

## What it does

Paste Sinhala text, press **Check**, and the app returns:

- **Corrected text** in its own window, ready to copy.
- A list of **errors** — each with the original word, the correction, a type
  (`spelling`, `grammar`, `grammar_discord`, `encoding_error`), and a bilingual
  (Sinhala + English) explanation.
- A short **summary** in both languages.

The proofreading is driven by a detailed Sinhala-linguistics system prompt that
is deliberately conservative — it ignores English words, Sri Lankan proper
nouns, numbers/dates/currency, and valid colloquial/inflected/reduplicated forms,
and only flags an error when confidence is ≥ 0.75 (≥ 0.85 for colloquial text).
A missed error is preferred over a false positive on valid Sinhala.

### Self-learning corrections

When a reviewer edits the corrected text and saves it, the word-level changes are
captured into a corrections database. Over time:

- **Inject** — top human-verified corrections are added to the Gemini prompt as
  few-shot examples, improving accuracy for everyone.
- **Pre-check** — once a correction is *confirmed* and seen ≥ N times, it's
  applied **instantly and locally** (no Gemini call), which is faster and saves
  API quota.

In LAN mode this database lives centrally on the Control PC; clients sync it on
startup. The store is **SQLite** (`corrections.db`) — thread-safe and robust; an
older `corrections.json` is migrated automatically on first run (kept as
`corrections.json.bak`).

---

## Two connection modes

Chosen in **Settings → Connection Mode**. Both ultimately use Gemini — the
difference is *where* the call happens and *where* the API key lives.

```
DIRECT MODE                          LAN PROXY MODE (recommended for many clients)
-----------                          ---------------------------------------------
[Client .exe] --HTTPS--> Gemini      [Client .exe] --HTTP/LAN--> [Control PC] --HTTPS--> Gemini
  (API key on each client)             (no key, no internet)      (only PC online; holds the key)
```

| | Direct | LAN Proxy |
|---|---|---|
| API key location | each client PC | Control PC only |
| Internet needed on client | yes | **no** |
| Best for | a few standalone machines | many locked-down clients on one LAN |

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full Control PC + client setup.

---

## Quick start (development)

```powershell
pip install -r requirements.txt
python main.py
```

- Open **Settings** (top-right ⚙️) to set the API key, connection mode, model,
  theme, and UI language.
- Shortcuts: **Ctrl+Enter** = check, **Ctrl+L** = clear.
- Get a free Gemini API key at <https://aistudio.google.com/app/apikey>.

### Where the API key comes from (Direct mode)

Resolved in priority order:

1. The saved per-user config (`~/.sinhala_proofreader/config.json`)
2. The `GEMINI_API_KEY` environment variable
3. A `gemini_key.txt` file (one line) placed next to the `.exe`

Option 3 makes mass deployment easy — drop one key file beside the `.exe` and
every client picks it up. In **LAN Proxy** mode the client needs no key at all.

---

## Build the standalone .exe

```powershell
python -m PyInstaller build.spec --clean --noconfirm
```

…or just double-click **`build.bat`** (installs deps + builds). Output:
`dist/SinhalaProofreader.exe` — single-file, windowed, self-contained. Close any
running copy first (it locks the output file). Full details in [BUILD.md](BUILD.md).

### Versioning

The version lives in one place — [version.py](version.py). Bump it with:

```powershell
python bump_version.py            # patch:  4.3.0 -> 4.3.1
python bump_version.py minor      # minor:  4.3.0 -> 4.4.0
python bump_version.py major      # major:  4.3.0 -> 5.0.0
python bump_version.py 4.5.2      # explicit version
```

The app icon (window, taskbar, and the `.exe`) comes from `assets/icon.png`. The
build embeds `assets/icon.ico` (a square multi-size icon generated from the PNG);
if you change the PNG, regenerate the `.ico` so the EXE/taskbar stay in sync.

---

## Tests

```powershell
$env:PYTHONUTF8=1; python tests/test_app.py      # engine + orchestrator + corrections DB (no key/internet)
$env:PYTHONUTF8=1; python tests/test_engine.py   # LIVE Gemini call (skips if no key)
```

---

## Project layout

```
version.py · main.py · config.py
engine/    gemini_engine.py · lan_proxy_engine.py · proofreader.py · corrections_db.py · utils.py
gui/       main_window.py · settings_dialog.py · welcome_dialog.py · widgets.py · theme.py · i18n.py
proxy_server/   Flask Control-PC server + web admin panel (see README_CONTROL_PC.txt)
assets/ · requirements.txt · build.spec · build.bat · bump_version.py
```

- **`engine/proofreader.py`** — orchestrator; selects the engine (direct vs. proxy)
  and never crashes the GUI (failures become structured `ok=False` results).
- **`engine/gemini_engine.py`** — context-aware Gemini proofreading + the Sinhala
  system prompt; classifies API errors into friendly bilingual messages.
- **`engine/lan_proxy_engine.py`** — client engine that POSTs to the Control PC.
- **`engine/corrections_db.py`** — thread-safe, self-learning corrections store
  on **SQLite** (shared by client and proxy; auto-migrates old JSON).
- **`proxy_server/gemini_rest.py`** — the proxy's Gemini client over plain HTTPS
  REST (`requests` only — no deprecated SDK); also lists the key's available
  models to populate the admin model dropdown.
- **`proxy_server/`** — the Flask server for the Control PC, plus an admin panel
  and the Windows `.bat` helpers (`INSTALL`, `START_PROXY`, `FIREWALL_SETUP`,
  `CHECK_LAN_IP`, `AUTOSTART_SETUP`, …).

### Where user data lives

Per-user, outside the app (survives restarts and `.exe` updates):

```
~/.sinhala_proofreader/config.json        settings + API key (Direct mode)
~/.sinhala_proofreader/corrections.db      learned corrections cache (SQLite)
```

---

## Notes

- **Transport:** all Gemini calls use plain HTTPS REST (not gRPC) so locked-down
  firewalls/proxies handle them cleanly. The Control PC proxy calls Gemini
  directly with `requests` (no SDK — avoids the deprecated `google-generativeai`
  package, which 404s on Python 3.14). Whitelist
  `generativelanguage.googleapis.com:443` on whichever PC goes out; LAN clients
  in proxy mode only need to reach the Control PC on **TCP 8765**.
- **Model:** default is `gemini-2.5-flash` (good Sinhala + generous free quota).
  The proxy admin panel has a **model dropdown** populated from your key's real
  models, and **auto-switches** off a retired/unavailable model (e.g. the old
  `gemini-2.0-flash`). Avoid `*-pro` for many shared users — its free quota is low.
- **Quota:** many users on a *free* key will hit `429`. Enable billing on the
  Google Cloud project, pick a `flash` model, and/or raise `max_concurrent`
  in the proxy admin panel.
- **Encoding:** UTF-8 throughout; all text is normalized to NFC. The GUI never
  prints to stdout, so the Windows cp1252 console limitation only affects test
  scripts (hence `PYTHONUTF8=1`).
- **Admin panel:** `http://localhost:8765/admin` on the Control PC (default
  password `admin123` — change it on first login).

See [DEPLOYMENT.md](DEPLOYMENT.md) and [BUILD.md](BUILD.md) for the full guides.
