@echo off
chcp 65001 >nul
title Stop Sinhala Proxy
taskkill /fi "WINDOWTITLE eq SinhalaProxyServer" /f >nul 2>&1
rem Fallback: also free TCP port 8765 (covers hidden / service runs with no window)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8765" ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
echo Proxy server stopped (window titled SinhalaProxyServer, or anything on port 8765).
echo If it is still running, close its console window manually.
pause
