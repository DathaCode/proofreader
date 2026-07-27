@echo off
chcp 65001 >nul
title SinhalaProxyServer
cd /d "%~dp0"
echo ========================================
echo   Sinhala Proofreader Proxy Server
echo ========================================
py proxy.py
if errorlevel 1 (
    echo.
    echo ERROR: Server failed. Run INSTALL.bat first, and check api_key.txt.
    pause
)
