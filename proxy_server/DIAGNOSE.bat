@echo off
title Proxy Diagnostics - Sinhala Proxy
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ================================================================
echo   SINHALA PROXY - CONTROL PC DIAGNOSTICS
echo ================================================================
echo.

echo [1] This PC's LAN IP address(es)
echo ----------------------------------------------------------------
ipconfig | findstr /i "IPv4"
echo.
echo     Clients must use  http://THIS-IP:8765  in their Settings.
echo.

echo [2] Is the proxy running and listening on port 8765?
echo ----------------------------------------------------------------
set "OWNPID="
netstat -ano | findstr ":8765" | findstr "LISTENING"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8765" ^| findstr "LISTENING"') do (
    if not defined OWNPID set "OWNPID=%%p"
)
if not defined OWNPID (
    echo     RESULT: NOT LISTENING -- the proxy is NOT running.
    echo             Start it with START_PROXY.bat, then run this again.
) else (
    echo     RESULT: listening. Address must be 0.0.0.0:8765 [all interfaces].
    echo             If it shows only 127.0.0.1:8765, clients CANNOT connect.
    echo.
    echo     Which program owns port 8765:
    tasklist /FI "PID eq !OWNPID!" /FO LIST | findstr /i "Name PID"
    echo     Command line:
    powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter 'ProcessId=!OWNPID!' | Select-Object -ExpandProperty CommandLine" 2>nul
    echo.
    echo     This MUST be python.exe running proxy.py from THIS folder.
    echo     A different folder or program means something stole port 8765.
)
echo.

echo [3] Windows Firewall rule for TCP 8765
echo ----------------------------------------------------------------
netsh advfirewall firewall show rule name="SinhalaProofreadProxy" >nul 2>&1
if errorlevel 1 (
    echo     RESULT: RULE NOT FOUND -- run FIREWALL_SETUP.bat as administrator.
) else (
    netsh advfirewall firewall show rule name="SinhalaProofreadProxy" | findstr /i "Enabled Direction Action Profiles LocalPort"
    echo     RESULT: rule exists. Check Enabled=Yes, Action=Allow, LocalPort=8765.
)
echo.

echo [4] Firewall profiles and this PC's network category
echo ----------------------------------------------------------------
netsh advfirewall show allprofiles state
powershell -NoProfile -Command "Get-NetConnectionProfile | Select-Object Name,InterfaceAlias,NetworkCategory | Format-Table -AutoSize" 2>nul
echo.

echo [5] Local self-test   http://127.0.0.1:8765/status
echo ----------------------------------------------------------------
rem --noproxy "*" : ignore any http_proxy/https_proxy env var on this PC.
rem Without it curl would try to reach localhost THROUGH a corporate proxy
rem and report a false failure.
curl -s -m 5 --noproxy "*" http://127.0.0.1:8765/status
if errorlevel 1 (
    echo     RESULT: FAILED -- proxy not responding on this PC itself.
    echo             A firewall NEVER blocks this test, so if it fails the
    echo             problem is the server process, not the network.
) else (
    echo.
    echo     RESULT: OK -- proxy is alive locally.
)
echo.

echo [6] LAN self-test  [reach this PC through its own LAN IP]
echo ----------------------------------------------------------------
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set "IP=%%a"
    set "IP=!IP: =!"
    echo     Testing http://!IP!:8765/status
    curl -s -m 5 --noproxy "*" http://!IP!:8765/status
    echo.
)
echo.

echo [7] Which LAN clients are connected RIGHT NOW?
echo ----------------------------------------------------------------
netstat -an | findstr ":8765" | findstr "ESTABLISHED"
if errorlevel 1 (
    echo     RESULT: no client is connected at this moment.
    echo             NOTE: this is normal when clients are idle - they only
    echo             hold a connection while a correction is being sent.
) else (
    echo     RESULT: the addresses above are clients connected right now.
)
echo.

echo [8] Is a system proxy configured on this PC?
echo ----------------------------------------------------------------
set http_proxy 2>nul
set https_proxy 2>nul
set no_proxy 2>nul
echo     [blank above = no proxy env vars, which is what we want]
echo.

echo [9] Is an old SinhalaProxy Windows service also running?
echo ----------------------------------------------------------------
sc query SinhalaProxy 2>nul | findstr /i "SERVICE_NAME STATE"
if errorlevel 1 (
    echo     No SinhalaProxy service installed [normal if you use START_PROXY.bat].
) else (
    echo     A service exists. If it is RUNNING it may be holding port 8765
    echo     with an OLD copy of the code. Stop it: UNINSTALL_SERVICE.bat
)
echo.

echo [10] Last 25 lines of the server log
echo ----------------------------------------------------------------
if exist "%~dp0data\server.log" (
    powershell -NoProfile -Command "Get-Content '%~dp0data\server.log' -Tail 25"
) else (
    echo     data\server.log not found.
    echo     [normal if you started the proxy with START_PROXY.bat, which
    echo      shows its output in its own console window instead]
)
echo.

echo [11] Is port 8765 inside a Windows reserved range?
echo ----------------------------------------------------------------
netsh interface ipv4 show excludedportrange protocol=tcp
echo     If 8765 falls inside any range above, Windows/Hyper-V reserved it.
echo     Fix: change "port" in proxy_config.json to 9765 and update clients.
echo.

echo [12] Full network configuration [mask + gateway]
echo ----------------------------------------------------------------
ipconfig | findstr /i "IPv4 Subnet Gateway"
echo.
echo     Compare these with the OLD Control PC. A wrong Subnet Mask or a
echo     missing/wrong Default Gateway lets packets ARRIVE from another
echo     subnet but stops the replies getting back - which looks exactly
echo     like "client cannot connect".
echo.
set "GW="
for /f "tokens=2 delims=:" %%g in ('ipconfig ^| findstr /i "Default Gateway" ^| findstr /r "[0-9]"') do (
    if not defined GW set "GW=%%g"
)
if not defined GW (
    echo     RESULT: NO DEFAULT GATEWAY SET. This PC cannot talk to any
    echo             other subnet. That alone explains the failure.
) else (
    set "GW=!GW: =!"
    echo     Pinging default gateway !GW! ...
    ping -n 2 !GW!
)
echo.

echo ================================================================
echo  ON A CLIENT PC, open PowerShell and run:
echo      Test-NetConnection CONTROL-PC-IP -Port 8765
echo  TcpTestSucceeded : True   = network path is OK
echo  Or open in a browser:  http://CONTROL-PC-IP:8765/status
echo ================================================================
echo.
pause
