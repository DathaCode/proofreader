@echo off
chcp 65001 >nul
title Autostart Setup - Sinhala Proxy
cd /d "%~dp0"
rem Auto-start the proxy HIDDEN (via run_hidden.vbs) every time this user logs in.
rem No console window appears, so users cannot close it.
schtasks /create /tn "SinhalaProofreadProxy" /tr "wscript.exe \"%~dp0run_hidden.vbs\"" /sc onlogon /f
if errorlevel 1 (
    echo.
    echo FAILED to create the scheduled task. Try running as administrator.
) else (
    echo.
    echo Done. The proxy will auto-start HIDDEN whenever this user logs in.
    echo There is no window to close.
    echo.
    echo To start it now without rebooting, run START_HIDDEN.bat
    echo To stop it, run STOP_PROXY.bat
    echo To remove autostart:  schtasks /delete /tn "SinhalaProofreadProxy" /f
)
pause
