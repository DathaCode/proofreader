FROM python:3.11-slim

WORKDIR /app

# psycopg2-binary ships wheels, so no build toolchain is needed.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY app.py config.py database.py auth.py corrections_db.py usage_logger.py \
     gemini_web.py gemini_rest.py lang_detect.py migrate_sqlite_to_pg.py ./
# Per-language proofreading prompts
COPY sinhala_system_prompt.txt tamil_system_prompt.txt english_system_prompt.txt ./
COPY templates/ templates/
COPY static/ static/

# NOTE: api_key.txt is NOT copied — it is gitignored and optional.
# The key normally comes from GEMINI_API_KEY in .env (env_file).

RUN mkdir -p /app/data

EXPOSE 5000

# Single worker + threads: the in-memory rate limiter is per-process, and the
# workload is I/O-bound (Gemini calls), so threads give the concurrency.
CMD ["gunicorn", "-w", "1", "--threads", "16", "--timeout", "180", \
     "-b", "0.0.0.0:5000", "--access-logfile", "-", "app:app"]
