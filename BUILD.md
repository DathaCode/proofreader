# Sinhala Proofreader — Build & Versioning

Gemini-powered Sinhala spell + grammar checker with a self-learning corrections
database. Two connection modes: **Direct** (Gemini API key on the PC) and
**LAN Proxy** (via a Control PC — see `DEPLOYMENT.md` / `proxy_server/`).
Modern UI with dark + light themes and English/Sinhala switching.

Python 3.9+ (3.14 OK) · Windows 10/11 64-bit. Current version: **4.3.0**.

## 1. Install dependencies
```powershell
pip install -r requirements.txt
```

## 2. Run (dev)
```powershell
python main.py
```
- Settings (top-right ⚙️) holds the API key, connection mode, model, theme and UI language.
- Shortcuts: **Ctrl+Enter** = check, **Ctrl+L** = clear.
- The corrected text opens in its own window; Input and Results split the main window 50/50.

## 3. Run tests (no key / no internet needed)
```powershell
$env:PYTHONUTF8=1; python tests/test_app.py      # engine + orchestrator + corrections DB
$env:PYTHONUTF8=1; python tests/test_engine.py   # LIVE Gemini (skips if no key)
```

## 4. Build the standalone .exe
One command (either form works):
```powershell
python -m PyInstaller build.spec --clean --noconfirm
```
…or just double-click **`build.bat`** (installs deps + builds).

Output: `dist/SinhalaProofreader.exe` — single-file, windowed, self-contained.
Before building, close any running `SinhalaProofreader.exe` (it locks the output file):
```powershell
Get-Process SinhalaProofreader -ErrorAction SilentlyContinue | Stop-Process -Force
```

## 5. Change the version
The version lives in one place: **`version.py`** (`__version__`). The window title
shows it. Use the script:
```powershell
python bump_version.py            # patch:  4.3.0 -> 4.3.1
python bump_version.py minor      # minor:  4.3.0 -> 4.4.0
python bump_version.py major      # major:  4.3.0 -> 5.0.0
python bump_version.py 4.5.2      # set an explicit version
```
Then rebuild (step 4). Typical release flow:
```powershell
python bump_version.py minor
python -m PyInstaller build.spec --clean --noconfirm
```

## Where settings live
Per-user, outside the app (survives restarts and .exe updates):
```
~/.sinhala_proofreader/config.json        settings + API key (Direct mode)
~/.sinhala_proofreader/corrections.db      learned corrections cache (SQLite)
```
For mass deployment you can instead drop a `gemini_key.txt` (one line) next to the
.exe, or set the `GEMINI_API_KEY` env var. In LAN Proxy mode the client needs no key.

## Project layout
```
version.py · main.py · config.py
engine/   gemini_engine.py · lan_proxy_engine.py · proofreader.py · corrections_db.py · utils.py
gui/      main_window.py · settings_dialog.py · welcome_dialog.py · widgets.py · theme.py · i18n.py
proxy_server/   Flask Control-PC server + admin panel (see README_CONTROL_PC.txt)
assets/ · requirements.txt · build.spec · build.bat · bump_version.py
```

## Notes
- **Encoding:** UTF-8 throughout. The GUI never prints to stdout, so the Windows
  cp1252 console limitation only affects test scripts (hence `PYTHONUTF8=1`).
- **Icon:** the app icon is `assets/icon.png`. `build.spec` embeds
  `assets/icon.ico` (a square, multi-size icon generated from the PNG) for the EXE
  and bundles both into the app so the window/taskbar icon loads at runtime. If
  you replace `icon.png`, regenerate `icon.ico` (e.g. with Pillow) to keep them
  in sync.
- **Corrections store:** SQLite (`corrections.db`). The class auto-migrates an old
  `corrections.json` on first run (→ `corrections.json.bak`). `sqlite3` is in the
  Python stdlib, so no extra dependency and no `build.spec` change is needed.
- **Quota:** 20 LAN users on a *free* key will hit 429 — enable billing and/or use
  a `flash` model (default `gemini-2.5-flash`). See `DEPLOYMENT.md`.

## Control PC proxy build
The proxy isn't packaged as an .exe — it runs from source on the Control PC via
`proxy_server/INSTALL.bat` (installs **flask + requests** only) and
`START_PROXY.bat`. It has **no** `google-generativeai` dependency; it calls Gemini
over plain HTTPS REST (`proxy_server/gemini_rest.py`). See `DEPLOYMENT.md`.
