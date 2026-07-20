@echo off
chcp 65001 >nul
cd /d F:\projects\proofreader\webapp
set /p BACKUP_FILE="Enter backup file path (e.g. data\backups\backup_20260717_1430.sql): "
if not exist "%BACKUP_FILE%" (
  echo File not found: %BACKUP_FILE%
  pause
  exit /b 1
)
echo WARNING: this overwrites the current database.
set /p CONFIRM="Type YES to continue: "
if /i not "%CONFIRM%"=="YES" (
  echo Cancelled.
  pause
  exit /b 0
)
docker compose exec -T db psql -U sinhala_admin -d sinhala_proofreader < "%BACKUP_FILE%"
echo Restore complete.
pause
