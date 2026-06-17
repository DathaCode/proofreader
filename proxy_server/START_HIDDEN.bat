@echo off
chcp 65001 >nul
title Start Sinhala Proxy (background)
cd /d "%~dp0"
echo Starting the Sinhala proxy in the BACKGROUND (no window)...
wscript.exe "%~dp0run_hidden.vbs"
echo.
echo Done. The server is now running with NO visible window,
echo so users cannot accidentally close it.
echo.
echo   Logs : data\server.log
echo   Stop : STOP_PROXY.bat
echo   Check: open http://localhost:8765/status  in a browser
timeout /t 5 >nul
