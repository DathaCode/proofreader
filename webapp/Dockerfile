FROM python:3.11-slim

WORKDIR /app

# sqlite3 CLI: lets `make db-check` and `docker compose exec web sqlite3 ...`
# inspect the DB (e.g. verify WAL mode) from inside the container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (proofreading logic reuses corrections_db.py + gemini_rest.py)
COPY app.py web_config.py gemini_web.py gemini_rest.py lang_detect.py corrections_db.py usage_logger.py ./
COPY sinhala_system_prompt.txt tamil_system_prompt.txt english_system_prompt.txt ./
# NOTE: api_key.txt is NOT copied — it is gitignored and provided at runtime.
# The key is set via the admin panel and persisted in the mounted data/ volume.
COPY templates/ templates/
COPY static/ static/

# Runtime data (corrections.db, usage_log.csv, web_config.json) — volume-mounted
RUN mkdir -p /app/data

EXPOSE 5000

CMD ["python", "-u", "app.py"]
