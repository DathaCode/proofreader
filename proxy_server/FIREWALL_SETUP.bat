@echo off
title Firewall Setup - Sinhala Proxy
cd /d "%~dp0"

rem Opens inbound TCP 8765 so LAN clients can reach this Control PC.
rem
rem NOTE: this file is deliberately pure ASCII and does NOT call "chcp".
rem cmd.exe tracks its position in a .bat as a byte offset; running chcp in a
rem script that also contains non-ASCII characters makes it lose that position
rem and execute garbage (stray "is not recognized" errors + repeated elevation
rem prompts). Keep this file ASCII-only.

rem --- Already Administrator? Reading the LOCAL SERVICE hive requires admin.
rem     (More reliable than "net session", which needs the Server service.)
reg query "HKU\S-1-5-19" >nul 2>&1
if not errorlevel 1 goto :isadmin

rem --- Not elevated: relaunch ONCE. The "retry" guard prevents an endless loop.
if /i "%~1"=="retry" goto :cantelevate
echo Requesting Administrator rights...
powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0' -ArgumentList 'retry'"
exit /b

:cantelevate
echo.
echo Could not obtain Administrator rights.
echo Right-click FIREWALL_SETUP.bat and choose "Run as administrator".
echo.
pause
exit /b 1

:isadmin
echo Adding Windows Firewall rule for TCP port 8765 (all network profiles)...
rem profile=any covers Public/Private/Domain - a freshly networked PC is often
rem classified as "Public", which a private-only rule would NOT match.
netsh advfirewall firewall delete rule name="SinhalaProofreadProxy" >nul 2>&1
netsh advfirewall firewall add rule name="SinhalaProofreadProxy" dir=in action=allow protocol=TCP localport=8765 profile=any
if errorlevel 1 goto :failed
echo.
echo Done. Clients on the LAN can now reach this PC on port 8765.
echo.
pause
exit /b 0

:failed
echo.
echo FAILED to add the firewall rule.
echo.
pause
exit /b 1
