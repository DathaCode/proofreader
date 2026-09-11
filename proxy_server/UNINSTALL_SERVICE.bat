@echo off
title Uninstall Sinhala Proxy Service
cd /d "%~dp0"

reg query "HKU\S-1-5-19" >nul 2>&1
if not errorlevel 1 goto :isadmin
if /i "%~1"=="retry" (
    echo Could not obtain Administrator rights.
    echo Right-click this file and choose "Run as administrator".
    pause
    exit /b 1
)
echo Requesting Administrator rights...
powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0' -ArgumentList 'retry'"
exit /b
:isadmin

set "NSSM="
if exist "%~dp0nssm.exe" set "NSSM=%~dp0nssm.exe"
if not defined NSSM ( where nssm >nul 2>&1 && set "NSSM=nssm" )
if not defined NSSM (
    echo nssm.exe not found - removing via sc instead...
    sc stop SinhalaProxy >nul 2>&1
    sc delete SinhalaProxy
    pause & exit /b
)

"%NSSM%" stop SinhalaProxy
"%NSSM%" remove SinhalaProxy confirm
echo.
echo Service "SinhalaProxy" removed.
pause
