================================================================
  SINHALA PROOFREADER — CONTROL PC PROXY SERVER
================================================================

WHAT THIS SERVER DOES
---------------------
This is the ONE machine on your LAN that talks to Google Gemini. The 20 client
PCs send their Sinhala text to this server; this server calls Gemini (applying
the shared self-learning corrections database) and returns the results. The
clients themselves never need internet and never hold the API key.

It also serves a web admin panel at  http://localhost:8765/admin  where you can
view/manage corrections, see usage, and change settings.

The server runs on Waitress, a production-grade WSGI server (installed by
INSTALL.bat) — not Flask's built-in dev server. Nothing to configure; if you
ever see "development server" in the console output, run INSTALL.bat again to
install waitress (or:  pip install waitress).

PREREQUISITES
-------------
- Windows 10/11
- Python 3.9+ installed and on PATH  (https://www.python.org/downloads/)
- This Control PC has internet access to  generativelanguage.googleapis.com:443
- The Control PC and all clients are on the same LAN
- A Google Gemini API key (https://aistudio.google.com/app/apikey)

FIRST-TIME SETUP (do once)
--------------------------
1. Run  INSTALL.bat              (installs flask, requests, waitress)
2. Open api_key.txt, replace the placeholder with your Gemini API key, save.
3. (Optional) edit sinhala_system_prompt.txt — the proofreading instructions.
4. Right-click FIREWALL_SETUP.bat -> "Run as administrator"  (opens port 8765)
5. Run  START_PROXY.bat          (starts the server; keep the window open)
6. Run  CHECK_LAN_IP.bat         (shows this PC's LAN IP, e.g. 192.168.1.100)
7. (Optional) Run AUTOSTART_SETUP.bat so the server starts on Windows login.

DAILY USE
---------
- Just run  START_PROXY.bat  (or it auto-starts if you ran AUTOSTART_SETUP.bat).
- Leave the console window open while clients are working.
- Run  STOP_PROXY.bat  to stop it.

RUN IN THE BACKGROUND (so users cannot close it)
------------------------------------------------
START_PROXY.bat shows a console window that a user might close. To run with NO
window, pick ONE of these:

  OPTION 1 — Hidden window (no install needed) [RECOMMENDED, EASIEST]
    - Run  START_HIDDEN.bat   -> the server runs with NO visible window.
    - Run  AUTOSTART_SETUP.bat -> it also auto-starts HIDDEN every time this
      user logs in. There is no window for anyone to close.
    - Logs go to  data\server.log .  Stop it with  STOP_PROXY.bat .
    - Check it is alive: open  http://localhost:8765/status  in a browser.

  OPTION 2 — Windows Service (most robust) [survives logout, auto-restarts]
    - One-time: download NSSM from  https://nssm.cc/download , unzip, and copy
      nssm.exe (the win64 one) into this folder.
    - Right-click  INSTALL_SERVICE.bat  -> Run as administrator.
    - Now it runs as the "SinhalaProxy" Windows service: starts on boot, keeps
      running after you log out, and auto-restarts if it crashes.
    - Manage it in  services.msc , or remove with  UNINSTALL_SERVICE.bat .
    - Logs go to  data\server.log .

Note: do NOT run more than one of START_PROXY / START_HIDDEN / the service at the
same time — they all use port 8765. Stop one before starting another.

ADMIN PANEL
-----------
Open  http://localhost:8765/admin  in a browser ON THE CONTROL PC.
For security it refuses other PCs on the LAN (they get "only available on the
Control PC"); proofreading for clients is not affected. To allow LAN access
anyway: Settings -> This Control PC -> untick "Admin panel only on this PC".
Default password: admin123  (the dashboard warns until you change it under
Settings -> Admin password).

Pages:
  Dashboard    today / this week / this month with trends, daily chart, busiest
               hours, who is online now (updates every 15 s), server health
  Clients      every client PC: online dot, PC name, Windows user, app version,
               usage + estimated cost. Type a NAME next to each PC and press the
               check mark - names then appear everywhere instead of IP addresses.
  Logs         every request; filter by period, month, date range, Control PC,
               client, status; "Export these rows (CSV)"
  Reports      per-client totals + estimated Gemini cost for any month/range;
               Download CSV or Print / Save PDF
  Corrections  learned corrections: search, filter, auto-fix / hint / disable
  Settings     API key + model, long-text limits, Gemini prices, server name,
               client update notice, admin password
  Data & Merge combine the logs of both Control PCs (see below)

LONG TEXTS (v5)
---------------
Clients can check up to "Max words per check" (default 5,000). The server splits
long text into ~250-word parts at paragraph/sentence breaks, checks the parts in
parallel ("Parallel Gemini calls", default 4) and joins the result. One check =
one row in the logs, whatever its length. Both limits are in Settings.

Each part may take up to "Timeout per call" (default 120 s) and is retried once if
Gemini is busy or slow; the client app waits accordingly (it learns the timing
from this server). Recommended for ~20 clients: Parallel Gemini calls = 8.

CAPACITY - HOW MANY CLIENTS PER CONTROL PC?
-------------------------------------------
The Control PC itself is never the limit (it only waits on the network). The
limits are (1) "Parallel Gemini calls" - every client shares these slots - and
(2) your Google project's Gemini rate limits (see aistudio.google.com/rate-limit).
Gemini limits are PER GOOGLE PROJECT, not per key or per PC: two Control PCs
using keys from the SAME project share ONE quota (good for backup, but it does
not add capacity). Guide, with Parallel calls = 8:
  up to ~25 clients    comfortable (typical short checks + some long ones)
  25 - 40 clients      OK with gemini-2.5-flash, or raise Parallel calls to 12
  40+ clients          split clients over two Control PCs whose keys come from
                       DIFFERENT Google projects (two separate quotas)

ESTIMATED GEMINI COST
---------------------
Every request records the exact token counts Gemini reports; cost = tokens x the
price table in Settings -> Gemini prices (USD per 1M tokens, paid-tier rates; a
free-tier key is not actually billed). Older requests from before v5 have no
token data: once 20+ new requests exist, their cost is ESTIMATED from the
measured cost per word and shown with a "~". Optionally set "LKR per 1 USD" to
also see rupees.

TWO CONTROL PCs (e.g. .102 and .246)
------------------------------------
Each Control PC keeps its own log. To see ONE combined report:
  1. On each PC: Settings -> This Control PC -> Server name, e.g. "Control PC .102"
     (tick "also relabel this server's existing log rows").
  2. On the OTHER PC: Logs -> period "All time" -> "Export these rows (CSV)", and
     Data & Merge -> "Client names (JSON)".
  3. On this PC: Data & Merge -> Import usage logs (the CSV) and Import client
     names (the JSON).
  4. Reports -> leave "All servers" selected.
Importing is safe to repeat: identical requests are matched, never duplicated,
even when both PCs share old history. If this PC's data folder was originally
COPIED from the other PC, use Data & Merge -> "Fix the Control PC label on old
rows" to move the copied history (up to the copy date) to the other PC's name.

UPGRADING A CONTROL PC TO v5
----------------------------
1. STOP_PROXY.bat
2. Copy the new proxy_server files over the old ones. KEEP: data\ folder,
   api_key.txt, proxy_config.json, backup_config.json.
3. START_HIDDEN.bat (or START_PROXY.bat). On first start the old
   data\usage_log.csv is imported into data\usage.db automatically (the CSV file
   is left untouched). The console shows "Usage rows: N".
4. Open the admin panel: set the server name, name your client PCs, change the
   admin password if still default.
5. After the new SinhalaProofreader.exe is on the clients, set Settings ->
   Client app updates -> Latest client version = 5.0.0; any PC still running an
   old app is then flagged on the Clients page.
Old (v4) client apps keep working with a v5 server, and v5 apps work with a v4
server, so PCs can be upgraded in any order.

TELLING CLIENTS THE PROXY URL
-----------------------------
On each client PC: open the app -> Settings -> Connection Mode -> "LAN Proxy",
and set Control PC URL to:   http://<Control-PC-IP>:8765   then Test + Save.

HOW CORRECTIONS LEARN
---------------------
When a reviewer edits the corrected text in the client app and clicks
"Save My Corrections", the change is sent here and stored. After a correction is
confirmed and seen >= "precheck_threshold" times, it is auto-applied instantly
(no Gemini call) and is also injected into the Gemini prompt for everyone.

BACKUP
------
data\corrections.db = your learned corrections; data\usage.db = usage logs,
client names and costs. BACKUP_S3.bat / BACKUP_SETUP.bat back up both nightly
(see BACKUP_README.txt). Admin -> Data & Merge also downloads copies.

TROUBLESHOOTING
---------------
Problem                 | Cause                    | Fix
------------------------+--------------------------+-------------------------------
Port in use             | Another app on 8765      | Change "port" in proxy_config.json, restart
API key invalid         | Wrong key in api_key.txt | Fix api_key.txt (or admin panel), restart
Clients can't connect   | Firewall                 | Run FIREWALL_SETUP.bat as Administrator
Slow / 429 errors       | Free-tier rate limits    | Enable billing on the Google project
"model not ready"       | No/blank API key         | Paste a key in api_key.txt or the admin panel
Too many users at once  | Concurrency limit        | Raise "max_concurrent" in admin Settings
Clients "not connected" | Many causes              | Run DIAGNOSE.bat on this PC (checks all)
Admin page says         | Opened from another PC   | Open http://localhost:8765/admin on the
 "only on Control PC"   |                          | Control PC itself (see ADMIN PANEL)
Empty data\server.log   | Old run_hidden.vbs       | Use the current run_hidden.vbs (py -u)
================================================================
