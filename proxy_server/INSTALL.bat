@echo off
chcp 65001 >nul
title Sinhala Proxy - First Time Setup
cd /d "%~dp0"
echo Installing Python packages...
pip install -r requirements_proxy.txt --quiet
if errorlevel 1 (
    echo FAILED. Ensure Python 3.9+ is installed and on PATH.
    pause & exit /b 1
)
if not exist "data" mkdir data
echo.
echo ================================
echo   INSTALL COMPLETE
echo ================================
echo.
echo NEXT STEPS:
echo 1. Open api_key.txt and paste your Gemini API key
echo 2. (Optional) edit sinhala_system_prompt.txt
echo 3. Run FIREWALL_SETUP.bat as Administrator
echo 4. Run START_PROXY.bat
echo 5. Run CHECK_LAN_IP.bat and give that URL to clients
echo ================================
pause
