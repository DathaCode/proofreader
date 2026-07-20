@echo off
chcp 65001 >nul
cd /d F:\projects\proofreader\webapp
if not exist data\backups mkdir data\backups
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set DT=%%I
set STAMP=%DT:~0,8%_%DT:~8,4%
set BACKUP_FILE=data\backups\backup_%STAMP%.sql
docker compose exec -T db pg_dump -U sinhala_admin sinhala_proofreader > "%BACKUP_FILE%"
echo Backup saved: %BACKUP_FILE%
pause
