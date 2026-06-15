# Master Skillset — Sinhala Proofreader Project

> Gemini-API-only desktop app (+ optional Control-PC LAN proxy). The offline
> dictionary/sinmorph engine is gone — don't reintroduce it.

## Prime Directives
1. ALWAYS read existing repo files before writing code.
2. ALWAYS use UTF-8 and normalize Sinhala to NFC before comparing/locating.
3. The orchestrator must NEVER crash the GUI — failures become `ok=False` results.
4. NEVER commit secrets: `proxy_server/api_key.txt`, `gemini_key.txt`, `config.json`
   are git-ignored. Don't run `git push` (the user pushes).
5. Keep `engine/corrections_db.py` and `proxy_server/corrections_db.py` IDENTICAL.
6. Default model is `gemini-2.5-flash`; `gemini-2.0-flash` is retired for new keys.

## Where things live
- Version: `version.py` (single source). Bump with `bump_version.py`.
- Client deps: `requirements.txt`. Proxy deps: `proxy_server/requirements_proxy.txt`
  (flask + requests only — no `google-generativeai`).
- User data (survives updates): `~/.sinhala_proofreader/config.json` and
  `corrections.db`. Proxy data: `proxy_server/data/corrections.db` + `usage_log.csv`.

## Critical Gotchas
- Sinhala chars are multi-byte in UTF-8 — use character positions, not byte offsets.
- tkinter Text positions are `"line.char"`, not absolute indexes.
- Bundled resources (icon, etc.) need `sys._MEIPASS` resolution when frozen:
```python
import sys, os
def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(__file__))
    return os.path.join(base, *parts)
```
- CustomTkinter needs tkinter (bundled with Python). Use a `tk.Text` for highlights.
- `sqlite3` connection is shared (`check_same_thread=False`) + guarded by a Lock;
  close it before deleting the DB file on Windows (file stays locked otherwise).
- Tests print Sinhala to stdout → run with `PYTHONUTF8=1` on Windows.

## Gemini call rules
- REST endpoint, `responseMimeType=application/json`, low temperature (~0.05).
- Only flag errors with confidence ≥ 0.75 (≥ 0.85 for colloquial); cap at 10.
- Protect English words + Sri Lankan proper nouns + numbers/dates — never flag them.
- A missed error is better than a false positive on valid Sinhala.

## Quality gates before an .exe build
- [ ] `python tests/test_app.py` and `tests/test_corrections_db.py` pass (PYTHONUTF8=1).
- [ ] App launches; Sinhala renders (not boxes); window/taskbar shows the icon.
- [ ] Direct mode: a known-error sentence returns corrections; key errors are friendly.
- [ ] LAN mode: Test Proxy works against a running Control PC; corrected text + copy work.
- [ ] Version bumped in `version.py`; `.exe` launches on a clean machine.

## Release flow
```powershell
python bump_version.py minor
python -m PyInstaller build.spec --clean --noconfirm   # -> dist/SinhalaProofreader.exe
```
Then the user pushes to git and distributes the `.exe`.
