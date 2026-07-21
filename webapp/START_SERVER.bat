@echo off
cd /d F:\projects\proofreader\webapp
echo Building and starting Sinhala Proofreader Web App...
docker compose up -d --build
echo.
echo ============================================================
echo  Server started.
echo  Users access:  http://sinhalaproof.duckdns.org
echo  Local test:    http://localhost
echo  Admin panel:   http://sinhalaproof.duckdns.org/admin
echo ============================================================
echo.
echo  Default logins:
echo    User : sinhala / proof123
echo    Admin: admin   / admin1234
echo.
echo  Set your Gemini API key in the Admin panel (or edit api_key.txt).
pause
