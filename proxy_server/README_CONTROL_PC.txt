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

PREREQUISITES
-------------
- Windows 10/11
- Python 3.9+ installed and on PATH  (https://www.python.org/downloads/)
- This Control PC has internet access to  generativelanguage.googleapis.com:443
- The Control PC and all clients are on the same LAN
- A Google Gemini API key (https://aistudio.google.com/app/apikey)

FIRST-TIME SETUP (do once)
--------------------------
1. Run  INSTALL.bat              (installs flask, google-generativeai, requests)
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
Open  http://localhost:8765/admin  in a browser on the Control PC.
Default password: admin123  (CHANGE IT on the dashboard immediately).
You can:
  - See stats + usage
  - Set / test the Gemini API key and model
  - View, add, search, confirm, set-precheck, disable, or delete corrections
  - Export / import the corrections.json database

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
Back up  data\corrections.json  regularly (this is your learned knowledge).
The admin panel's "Export JSON" button downloads a copy. usage_log.csv holds
the request history.

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
================================================================
