# Sinhala Proofreader — Deployment Guide

Two deployment models. Both use Gemini; the difference is **where** the Gemini
call happens and **where** the API key lives.

```
DIRECT MODE                         LAN PROXY MODE (recommended for 20 clients)
-----------                         ------------------------------------------
[Client .exe] --HTTPS 443--> Gemini   [Client .exe] --HTTP LAN--> [Control PC] --HTTPS 443--> Gemini
  (key on each client)                  (no key, no internet)       (the only PC online; holds the key)
```

The client app picks the mode in **Settings → Connection Mode**:
`Direct` (API key on this PC) or `LAN Proxy` (via Control PC, no key here).

---

## A) Direct mode — each client calls Gemini

For each client: Sophos must allow `generativelanguage.googleapis.com:443`
(HTTPS). Provision the key (config, `GEMINI_API_KEY` env var, or `gemini_key.txt`
next to the exe). See the endpoint table below.

Downside: the key sits on 20 machines and they share its quota.

## B) LAN Proxy mode — clients stay fully offline (recommended)

Only the **Control PC** reaches the internet. The 20 clients talk to it over the
LAN. The API key lives only on the Control PC. Clients need **zero** internet.

### Control PC checklist (one machine — see `proxy_server/README_CONTROL_PC.txt`)
1. Copy the `proxy_server/` folder to the Control PC.
2. `INSTALL.bat` → installs **flask + requests** (the proxy calls Gemini over
   plain HTTPS REST; no `google-generativeai` SDK).
3. Put your Gemini key in `api_key.txt` (or paste it in the admin panel).
4. `FIREWALL_SETUP.bat` → opens TCP 8765 for all network profiles. It now
   **self-elevates** (approve the UAC prompt) — no need to right-click "Run as
   administrator". `profile=any` covers a freshly-bridged VM that Windows tags
   as a *Public* network.
5. `START_PROXY.bat` → server runs on `http://0.0.0.0:8765`.
6. `CHECK_LAN_IP.bat` → note the LAN IP (e.g. `192.168.1.100`).
7. (Optional) `AUTOSTART_SETUP.bat` → auto-start on login.
8. Admin panel: `http://localhost:8765/admin` (default password `admin123` —
   change it). Save the key, then **pick a model from the dropdown** (it lists the
   models your key can actually use) and **Save Settings** — it verifies the model
   immediately. If a configured model is retired/unavailable, the proxy
   **auto-switches** to a working `flash` model. Manage corrections, usage, model,
   and key here.

Sophos on the Control PC must allow `generativelanguage.googleapis.com:443`.

### Client PC checklist (×20 — just the .exe)
1. Copy `dist/SinhalaProofreader.exe` to the client.
2. Launch → **Settings → Connection Mode → LAN Proxy**.
3. Set **Control PC URL** = `http://<Control-PC-IP>:8765` → **Test Proxy** → Save.
4. Done. No API key, no internet needed on the client.

---

## The Gemini endpoint (whitelist this on whichever PC goes out)

| | |
|---|---|
| **Host** | `generativelanguage.googleapis.com` |
| **Port** | `443` (HTTPS) |
| **URL** | `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=KEY` |

The app forces **REST transport** (plain HTTPS, not gRPC) so locked-down
firewalls/proxies handle it cleanly.

LAN-only requirement for clients in proxy mode: reach the Control PC on **TCP 8765**.

---

## Self-learning corrections

- A reviewer edits the corrected text in the client and clicks **Save My
  Corrections**. Word-level diffs are captured.
- In LAN mode they're sent to the Control PC and stored centrally in a **SQLite**
  DB (`proxy_server/data/corrections.db`); clients sync this on startup. An older
  `corrections.json` is migrated automatically on first run (kept as `.bak`).
- After a correction is **confirmed** and seen ≥ `precheck_threshold` times it is
  applied **instantly** (no Gemini call) and **injected** into the Gemini prompt
  for everyone — accuracy improves over time and saves API calls.
- Manage all of this in the admin panel.

---

## Security & quota notes
- **Key isolation:** in LAN mode the API key never leaves the Control PC and is
  never sent to clients.
- **Never commit the key:** `proxy_server/api_key.txt` is git-ignored (a tracked
  `api_key.txt.example` placeholder ships instead). If a real key was ever pushed,
  rotate it at <https://aistudio.google.com/app/apikey>.
- **Quota:** 20 users on a *free* key WILL hit `429`. **Enable billing** on the
  Google Cloud project for the key, use a `flash` model (default
  `gemini-2.5-flash`; avoid `*-pro` — low free quota), and/or raise
  `max_concurrent` in the admin panel. The proxy serializes load and can queue.
- The admin panel password defaults to `admin123` — change it on first login.
- The proxy uses Flask's dev server (fine for a 20-seat LAN). For hardening you
  can front it with a production WSGI server (waitress/gunicorn).
