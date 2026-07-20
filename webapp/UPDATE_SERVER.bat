@echo off
chcp 65001 >nul
cd /d F:\projects\proofreader\webapp
echo Pulling latest code...
git pull
echo Rebuilding and restarting...
docker compose up -d --build
echo.
echo Update complete. Data in the postgres_data volume is preserved.
docker compose ps
pause
