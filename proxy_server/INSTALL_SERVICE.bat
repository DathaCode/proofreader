@echo off
chcp 65001 >nul
title Install Sinhala Proxy as a Windows Service
cd /d "%~dp0"

rem --- Self-elevate to Administrator (services require admin) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator rights...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

rem --- Locate nssm.exe (next to this file, or on PATH) ---
set "NSSM="
if exist "%~dp0nssm.exe" set "NSSM=%~dp0nssm.exe"
if not defined NSSM ( where nssm >nul 2>&1 && set "NSSM=nssm" )
if not defined NSSM (
    echo.
    echo nssm.exe was not found.
    echo 1. Download NSSM from  https://nssm.cc/download
    echo 2. Unzip it and copy nssm.exe ^(win64^) next to this file:
    echo       %~dp0nssm.exe
    echo 3. Run this script again.
    echo.
    echo ^(Or just use START_HIDDEN.bat + AUTOSTART_SETUP.bat instead — no download needed.^)
    pause & exit /b 1
)

rem --- Find python.exe ---
set "PY="
for /f "delims=" %%p in ('where python 2^>nul') do if not defined PY set "PY=%%p"
if not defined PY (
    echo Python not found on PATH. Install Python 3.9+ first.
    pause & exit /b 1
)

if not exist "%~dp0data" mkdir "%~dp0data"

echo Installing service "SinhalaProxy" using:
echo   python : %PY%
echo   script : %~dp0proxy.py
"%NSSM%" install SinhalaProxy "%PY%" "proxy.py"
"%NSSM%" set SinhalaProxy AppDirectory "%~dp0"
"%NSSM%" set SinhalaProxy DisplayName "Sinhala Proofreader Proxy"
"%NSSM%" set SinhalaProxy Description "LAN proxy that forwards Sinhala proofreading requests to Gemini."
"%NSSM%" set SinhalaProxy Start SERVICE_AUTO_START
"%NSSM%" set SinhalaProxy AppStdout "%~dp0data\server.log"
"%NSSM%" set SinhalaProxy AppStderr "%~dp0data\server.log"
"%NSSM%" set SinhalaProxy AppExit Default Restart
"%NSSM%" start SinhalaProxy

echo.
echo ================================================
echo  Installed + started as Windows Service.
echo  - Runs in the background (no window)
echo  - Survives logout, starts on boot
echo  - Auto-restarts if it crashes
echo  Logs:   data\server.log
echo  Manage: services.msc  (or UNINSTALL_SERVICE.bat)
echo ================================================
pause
