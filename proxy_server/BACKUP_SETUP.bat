@echo off
chcp 65001 >nul
title Sinhala Proxy - Schedule S3 Backup
cd /d "%~dp0"
rem Registers a DAILY 2:00 AM backup to S3 (the cron equivalent on Windows).
rem The "scheduled" argument tells BACKUP_S3.bat not to pause.
schtasks /create /tn "SinhalaProxyBackup" /tr "\"%~dp0BACKUP_S3.bat\" scheduled" /sc daily /st 02:00 /f
if errorlevel 1 (
    echo.
    echo FAILED to create the scheduled task. Try running as administrator.
) else (
    echo.
    echo Done. A daily backup will run at 2:00 AM.
    echo   - Requires this PC to be ON and this user logged in at 2 AM.
    echo   - Test it now:  BACKUP_S3.bat
    echo   - Remove it:    schtasks /delete /tn "SinhalaProxyBackup" /f
    echo   - View it:      Task Scheduler  ^>  SinhalaProxyBackup
)
pause
