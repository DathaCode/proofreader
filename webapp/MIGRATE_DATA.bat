@echo off
chcp 65001 >nul
cd /d F:\projects\proofreader\webapp
echo Migrating learned corrections from SQLite to PostgreSQL...
docker compose exec api python migrate_sqlite_to_pg.py
pause
