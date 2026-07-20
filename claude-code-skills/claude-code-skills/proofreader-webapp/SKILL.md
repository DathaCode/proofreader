# Proofreader WebApp Skill

## Purpose
Develop and operate the **production web version** of the Sinhala/Tamil/English
Proofreader (`webapp/`). This is a SEPARATE track from the desktop **.exe**
version (`gui/`, `main.py`, `engine/`) and the LAN **proxy** version
(`proxy_server/`). Never modify the .exe or proxy sources when working on the
webapp — they are maintained independently.

## When to Activate
- Any change under `F:\projects\proofreader\webapp\`
- PostgreSQL schema / users / sessions / corrections / logs / config
- Docker Compose stack (db + api + nginx + pgadmin)
- Multilingual UI (Sinhala / Tamil / English) — i18n, switcher, script auto-detect
- Auth: registration, admin approval, sessions, password change
- Deploying to the server (branch `prodlotus`)

## Architecture (v2 — PostgreSQL)
```
browser → nginx :80 → Flask/gunicorn api :5000 → Gemini REST
                              ↓
                        PostgreSQL (users, user_sessions, corrections,
                                    proofread_logs, password_resets, app_config)
   pgAdmin :5050 → PostgreSQL
```

| File | Role |
|------|------|
| `app.py` | Flask app: public/user/admin routes, cookie+DB sessions, rate limit |
| `database.py` | psycopg2 ThreadedConnectionPool; init retries while DB boots |
| `config.py` | env config + `DbConfig` adapter (lets `gemini_web.py` stay unchanged) |
| `auth.py` | users, sessions, password resets |
| `corrections_db.py` | self-learning corrections (PostgreSQL) |
| `usage_logger.py` | proofread/usage logging (PostgreSQL) |
| `gemini_web.py` + `gemini_rest.py` + `lang_detect.py` | multilingual engine (REST) |
| `*_system_prompt.txt` | si / ta / en proofreading prompts |
| `init_db.sql` | schema + seeded admin + app_config defaults |
| `migrate_sqlite_to_pg.py` | one-shot import of old SQLite corrections |
| `templates/` | `base.html` + `admin/*` + `user/*` (Jinja inheritance) |
| `static/css`, `static/js` | style + `app.js` + `i18n.js` |

## Non-obvious rules (LEARN THESE)
- **Passwords are plain SHA-256 hex** (`auth.hash_password`) to match the
  `init_db.sql` seed `encode(sha256('admin1234'),'hex')`. Both sides MUST agree
  or the admin can't log in. ⚠️ Weak for a public app — upgrade path is werkzeug
  PBKDF2 (re-hash admin on boot). Do not "fix" one side without the other.
- **`init_db()` runs at import** (`_bootstrap()` in app.py), not only in
  `__main__` — gunicorn never runs `__main__`, so the pool would be uninitialised.
- **Single gunicorn worker + threads** (`-w 1 --threads 16`): the in-memory rate
  limiter is per-process; multiple workers would multiply the limit.
- **Never `COPY api_key.txt`** in the Dockerfile and never bind-mount a single
  gitignored file — a clean checkout lacks it and Docker turns the missing mount
  into a directory. The Gemini key comes from `GEMINI_API_KEY` in `.env`.
- **pgAdmin rejects `.local` emails** — use a real TLD for `PGADMIN_EMAIL`.
- `init_db.sql` runs ONLY on an empty `postgres_data` volume. Schema changes need
  a migration or `docker compose down -v` (wipes data) on a dev box.
- The corrections `type` CHECK allows the engine's own values
  (`grammar_discord`, `encoding_error`) plus short forms.

## Operate
- Start: `START_SERVER.bat` (`docker compose up -d --build`)
- Migrate old data once: `MIGRATE_DATA.bat`
- Backup / restore: `backup_db.bat` / `restore_db.bat` (pg_dump to `data/backups/`)
- Fresh DB on a dev box: `docker compose down -v` then `up`
- Deploy: dev on `main` → merge to `prodlotus` → server `git pull` + `docker compose up -d --build`
- Default admin: `admin / admin1234` — CHANGE IT after first login.

## Verify after changes
`docker compose ps` (4 healthy) · `/status` returns `database:up` · admin login ·
register→approve→login · save correction shows in `/admin/corrections` ·
pgAdmin :5050 · `backup_db.bat` writes a `.sql`.
