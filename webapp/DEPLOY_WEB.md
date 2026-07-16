# AI Proofreader (Web) — Testing & Deployment Guide

Multilingual (සිංහල · தமிழ் · English) browser proofreader. Runs in Docker on a
server PC; users reach it over a public URL.

- **UI language switcher**: Si / Ta / En, remembered per browser. First visit
  defaults to the browser's language (`Accept-Language`), falling back to English.
- **Text language**: auto-detected from the pasted script (Sinhala / Tamil /
  Latin) and routed to the matching proofreading prompt. A "Text language"
  dropdown lets a user force a language instead of auto.

---

## 1. Prerequisites

1. **Docker Desktop** installed and running (`docker --version`, `docker compose version`).
2. A **Gemini API key** — get one free at https://aistudio.google.com → "Get API Key".
3. This folder: `F:\projects\proofreader\webapp`.

---

## 2. Test it locally (before going public)

### 2a. Start
```bat
cd F:\projects\proofreader\webapp
docker compose up -d --build
```
Open **http://localhost**.

### 2b. First-run setup
1. Log in as admin: **admin / admin1234**.
2. Go to the API-key box → paste your Gemini key → **Save key**. It auto-loads
   the model list and picks a working `flash` model.
3. Click **Test key** — you should see "OK — test proofread succeeded".
4. **Change both passwords** (Admin → Configuration → user/admin password).

### 2c. Functional test checklist
Log in as user (**sinhala / proof123**) and confirm each:

| # | Test | Expected |
|---|------|----------|
| 1 | Switch UI to த (Tamil), then EN, then සිං | All labels/buttons/placeholders change instantly; choice sticks after refresh |
| 2 | Paste Sinhala text with an error (`ලංකාවේ අද්‍යාපන ප්‍රශ්ණ ගොඩක් තිබේ.`) → Check | Results show, "Detected: Sinhala", red/orange highlights, error list |
| 3 | Paste Tamil (`வனக்கம், நான் தமில் நேசிக்கிறான்.`) → Check | "Detected: Tamil"; Tamil corrections (வணக்கம், தமிழ்) |
| 4 | Paste English (`I recieve teh mail.`) → Check | "Detected: English"; spelling fixes |
| 5 | Set "Text language" = Tamil, paste mixed text → Check | Forced to Tamil regardless of content |
| 6 | Edit the corrected box, click Save my corrections | "N corrections saved" toast |
| 7 | Rapidly click Check 12× | 11th–12th blocked (rate limit) |
| 8 | http://localhost/admin | Dashboard; corrections + usage populate |
| 9 | http://localhost/status | JSON `{"status":"online",...}` |
| 10 | Dark/light toggle (🌙/☀️) | Theme flips and sticks |

### 2d. Logs / stop
```bat
docker compose logs -f web      :: watch app logs
docker compose down             :: stop
```

> **Note on Tamil quality:** the Tamil proofreading prompt is solid but has not
> been tuned against a large Tamil corpus. Have a Tamil speaker review a few real
> documents and, if needed, refine `tamil_system_prompt.txt` (rebuild after edits).

---

## 3. Deploy on the server PC (Docker)

1. Copy the `webapp` folder to the server PC (or `git pull` the repo there).
2. Put the Gemini key in `api_key.txt` (or set it later in the admin panel).
3. Start:
   ```bat
   START_SERVER.bat            :: = docker compose up -d --build
   ```
   nginx serves on **port 80**; Flask runs on 5000 inside the Docker network.
4. Auto-start on boot: containers use `restart: unless-stopped`, so they come
   back after a reboot **as long as Docker Desktop is set to start on login**
   (Docker Desktop → Settings → General → "Start Docker Desktop when you sign in").
5. Persistent data lives in `webapp/data/` (corrections DB, usage log, config)
   and `api_key.txt` — both mounted as volumes, so `--build` upgrades never wipe them.

Stop with `STOP_SERVER.bat` (`docker compose down`).

---

## 4. Make it reachable on a public URL

You have two routes. **Cloudflare Tunnel is strongly recommended** — it solves
every "Cons/Risks" item from the plan (dynamic IP, ISP blocking 80/443, no SSL,
public port exposure) and needs no router changes.

### Option A — Cloudflare Tunnel (recommended: free HTTPS, no port-forwarding)

Gives you `https://proofreader.yourdomain.com` with automatic TLS. The tunnel
dials **out** from your PC to Cloudflare, so no inbound ports are opened and ISP
port-blocking is irrelevant.

1. Create a free Cloudflare account and add a domain (or use a subdomain you own).
2. Install `cloudflared` on the server PC: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
3. Authenticate and create the tunnel:
   ```bat
   cloudflared tunnel login
   cloudflared tunnel create proofreader
   cloudflared tunnel route dns proofreader proofreader.yourdomain.com
   ```
4. Point the tunnel at the local app (nginx on port 80). Create a config file
   `C:\Users\<you>\.cloudflared\config.yml`:
   ```yaml
   tunnel: proofreader
   credentials-file: C:\Users\<you>\.cloudflared\<TUNNEL-ID>.json
   ingress:
     - hostname: proofreader.yourdomain.com
       service: http://localhost:80
     - service: http_status:404
   ```
5. Run it (and install as a service so it survives reboot):
   ```bat
   cloudflared tunnel run proofreader
   cloudflared service install
   ```
6. Visit **https://proofreader.yourdomain.com** — done, with HTTPS.

> No domain? Run `cloudflared tunnel --url http://localhost:80` for an instant
> throwaway `https://<random>.trycloudflare.com` URL — great for quick demos.

### Option B — DuckDNS + router port-forward (matches the original plan)

Free `http://sinhalaproof.duckdns.org`, but HTTP-only and depends on your ISP
allowing inbound port 80.

1. Register a subdomain at https://www.duckdns.org (e.g. `sinhalaproof`).
2. Install the DuckDNS updater on the server PC so the dynamic IP stays current
   (DuckDNS provides a Windows `.bat` + Task Scheduler recipe).
3. On your router, **forward external port 80 → server PC's LAN IP : 80**.
   Reserve/set a static LAN IP for the PC (DHCP reservation) so it doesn't change.
4. Open Windows Firewall for inbound TCP 80:
   ```bat
   netsh advfirewall firewall add rule name="Proofreader 80" dir=in action=allow protocol=TCP localport=80
   ```
5. Visit **http://sinhalaproof.duckdns.org**.

**Caveats:** many home ISPs block inbound 80/443 or use CGNAT (no real public IP) —
if it doesn't work, that's why, and **Option A is the fix**. Option B is HTTP-only
(no encryption); if you must use it, add HTTPS via a reverse proxy + Let's Encrypt,
or just use Option A.

---

## 5. Security reminders before public exposure

- **Change the default passwords** (admin/user) in the admin panel first.
- The Gemini key stays server-side (never sent to the browser) and is gitignored.
- `/api/proofread` is rate-limited (default 10/min per IP — tune in admin config).
- Prefer **Option A (HTTPS)** for any real/public use; passwords over plain HTTP
  (Option B) can be sniffed.
- Consider raising the rate limit / adding accounts per team member as usage grows.
