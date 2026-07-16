FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (proofreading logic reuses corrections_db.py + gemini_rest.py)
COPY app.py web_config.py gemini_web.py gemini_rest.py lang_detect.py corrections_db.py usage_logger.py ./
COPY sinhala_system_prompt.txt tamil_system_prompt.txt english_system_prompt.txt api_key.txt ./
COPY templates/ templates/
COPY static/ static/

# Runtime data (corrections.db, usage_log.csv, web_config.json) — volume-mounted
RUN mkdir -p /app/data

EXPOSE 5000

CMD ["python", "-u", "app.py"]
