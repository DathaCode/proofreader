@echo off
chcp 65001 >nul
title Uninstall Sinhala Proxy Service
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting Administrator rights...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

set "NSSM="
if exist "%~dp0nssm.exe" set "NSSM=%~dp0nssm.exe"
if not defined NSSM ( where nssm >nul 2>&1 && set "NSSM=nssm" )
if not defined NSSM (
    echo nssm.exe not found — removing via sc instead...
    sc stop SinhalaProxy >nul 2>&1
    sc delete SinhalaProxy
    pause & exit /b
)

"%NSSM%" stop SinhalaProxy
"%NSSM%" remove SinhalaProxy confirm
echo.
echo Service "SinhalaProxy" removed.
pause
