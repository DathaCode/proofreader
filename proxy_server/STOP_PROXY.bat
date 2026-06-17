@echo off
chcp 65001 >nul
title Stop Sinhala Proxy
echo Stopping the Sinhala proxy (TCP port 8765)...
set "KILLED="
rem Kill whatever process is LISTENING on port 8765 (works for hidden runs too).
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1 && set "KILLED=1"
)
rem Also close any visible console window started with START_PROXY.bat.
taskkill /fi "WINDOWTITLE eq SinhalaProxyServer" /f >nul 2>&1
echo.
if defined KILLED (
    echo Proxy stopped.
) else (
    echo No proxy was running on port 8765.
)
pause
