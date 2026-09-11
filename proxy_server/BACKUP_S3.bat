@echo off
chcp 65001 >nul
title Sinhala Proxy - S3 DB Backup
cd /d "%~dp0"
echo ========================================
echo   Backing up DB files to Amazon S3
echo ========================================
py backup_db.py
if errorlevel 1 (
    echo.
    echo BACKUP DID NOT COMPLETE. See backup.log and the messages above.
    echo   - Set your bucket in backup_config.json
    echo   - Install AWS CLI v2 and run:  aws configure
    rem Pause only when run by a human (not the scheduler).
    if "%1"=="" pause
    exit /b 1
)
echo.
echo Done. See backup.log for history.
if "%1"=="" pause
