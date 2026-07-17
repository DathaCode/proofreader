Sinhala Proofreader — Web App
=============================

Browser-based replacement for the .exe client. Runs on a server PC via Docker;
users reach it over a public URL. Reuses the same proofreading logic and the
self-learning corrections DB as the LAN proxy version.

QUICK START
-----------
1. Install Docker Desktop and make sure it is running.
2. Double-click START_SERVER.bat  (builds + starts the containers).
3. Open http://localhost  in a browser.
4. Log in and set the Gemini API key in the Admin panel.

DEFAULT LOGINS
--------------
  User  : sinhala / proof123     (proofreader only)
  Admin : admin   / admin1234    (proofreader + admin dashboard)

Change both passwords from the Admin > Configuration section after first login.

ARCHITECTURE
------------
  Browser  ->  nginx (port 80)  ->  Flask app (port 5000)  ->  Gemini REST API
                                         |
                                    corrections.db (SQLite, self-learning)

FILES
-----
  app.py                     Flask server: auth, routes, rate limit, sanitization
  web_config.py              Config + sha256-hashed credentials + API key handling
  gemini_web.py              Proofreading engine (3-layer: precheck / inject / Gemini)
  gemini_rest.py             Gemini client over plain HTTPS REST (firewall-friendly)
  corrections_db.py          Shared self-learning corrections store (SQLite)
  usage_logger.py            CSV usage log
  sinhala_system_prompt.txt  The proofreading system prompt
  api_key.txt.example        Placeholder; the real key is set via the Admin panel
                             and saved to data/api_key.txt (persisted, gitignored)
  templates/                 index.html (proofreader), login.html, admin.html
  static/                    style.css, app.js
  data/                      Runtime: corrections.db, usage_log.csv, web_config.json

ENDPOINTS
---------
  GET  /                 Proofreader page          (login required)
  GET/POST /login        Login                     (public)
  GET  /logout           Clear session
  POST /api/proofread    Proofread text (JSON)     (login + rate limited)
  POST /api/corrections  Save manual corrections   (login)
  GET  /admin            Admin dashboard           (admin only)
  GET  /admin/corrections Corrections table (JSON)  (admin only)
  GET  /status           Health check (JSON)       (public)

NOTES
-----
* This web version is developed SEPARATELY from the LAN proxy sources; the
  proxy_server/ sources are unchanged.
* Uses the REST Gemini client (requests) rather than the deprecated
  google-generativeai SDK, so it runs on any Python (3.11 in Docker, 3.14 local).
* Session timeout: 8 hours. Rate limit: 10 /api/proofread requests per IP/min.
* No HTTPS by default (HTTP only) — put a TLS terminator in front for production.
