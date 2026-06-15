# Tech Stack for Sinhala Proofreader

> The app is **Gemini-API only** (the old offline dictionary / Levenshtein /
> sinmorph engine was removed). Proofreading happens in the cloud; the local code
> handles UI, orchestration, the self-learning corrections DB, and the LAN proxy.

## Client app (`SinhalaProofreader.exe`)
| Library | Version | Purpose |
|---|---|---|
| customtkinter | >=5.2.0 | Modern GUI (dark/light theme, EN/SI i18n) |
| google-generativeai | >=0.5.0 | Gemini calls in **Direct mode** only |
| requests | >=2.31.0 | LAN-proxy client + general HTTP |
| pyinstaller | >=6.0.0 | Package to a single `.exe` |
| Pillow | (dev only) | Generate `assets/icon.ico` from `icon.png` |

`requirements.txt` holds the runtime deps. `sqlite3` and `tkinter` are part of the
Python standard library — no install needed.

## Control PC proxy (`proxy_server/`)
| Library | Version | Purpose |
|---|---|---|
| flask | >=3.0.0 | HTTP server + `/admin` web panel |
| requests | >=2.31.0 | Calls Gemini over plain HTTPS REST |

`requirements_proxy.txt` — **no `google-generativeai`**. The proxy talks to Gemini
through `proxy_server/gemini_rest.py` (raw REST), which avoids the deprecated SDK
that 404s on Python 3.14.

## Gemini access — REST, not gRPC
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent?key=KEY`
- List models (powers the admin dropdown): `GET .../v1beta/models?key=KEY`
- Plain HTTPS (port 443) so locked-down firewalls handle it cleanly.
- Default model: `gemini-2.5-flash` (good Sinhala + free quota). `gemini-2.0-flash`
  is retired for new keys; the proxy auto-switches off unavailable models.

## Corrections storage — SQLite
- `engine/corrections_db.py` (client) and an identical `proxy_server/corrections_db.py`.
- One shared `sqlite3` connection (`check_same_thread=False`) serialized by a
  `threading.Lock()`; tables `corrections` + `metadata`.
- Auto-migrates a legacy `corrections.json` (same dir) on first run → `.bak`.

## Sinhala Unicode tokenizer (still used for English-word protection etc.)
```python
import re
def tokenize_sinhala(text):
    pattern = r'[඀-෿‍]+'            # Sinhala block + ZWJ
    return [(m.group(), m.start(), m.end()) for m in re.finditer(pattern, text)]
```

## CustomTkinter highlighted text
```python
# Use a tk.Text widget (CTkTextbox lacks tag support) for colored highlights.
text_widget.tag_config("spell_error",   background="#8B0000", foreground="white")
text_widget.tag_config("grammar_error", background="#8B4500", foreground="white")
text_widget.tag_add("spell_error", f"1.{start}", f"1.{end}")
```

## requirements.txt (client)
```
customtkinter>=5.2.0
google-generativeai>=0.5.0
requests>=2.31.0
pyinstaller>=6.0.0
```
