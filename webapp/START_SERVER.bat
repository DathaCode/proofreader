@echo off
chcp 65001 >nul
cd /d F:\projects\proofreader\webapp
echo Starting Sinhala Proofreader (db + api + nginx + pgadmin)...
docker compose up -d --build
echo.
echo ============================================================
echo  Server running:
echo     App:     http://localhost
echo     Admin:   http://localhost/admin
echo     pgAdmin: http://localhost:5050
echo ============================================================
echo  Default admin login: admin / admin1234  (CHANGE IT)
echo  Set the Gemini key in .env (GEMINI_API_KEY), then restart.
pause
