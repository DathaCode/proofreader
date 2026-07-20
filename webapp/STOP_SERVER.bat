@echo off
chcp 65001 >nul
cd /d F:\projects\proofreader\webapp
docker compose down
echo Server stopped.
pause
