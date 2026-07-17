# Python Packaging and Dependencies

## Dependency Files

### requirements.txt (Production — Pinned)
```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.0
pydantic-settings==2.5.0
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
alembic==1.13.2
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
structlog==24.4.0
python-dotenv==1.0.1
redis==5.1.0
httpx==0.27.2
python-multipart==0.0.9
prometheus-fastapi-instrumentator==7.0.0
```

### requirements-dev.txt
```txt
-r requirements.txt
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0
httpx==0.27.2
ruff==0.6.8
mypy==1.11.2
pip-audit==2.7.3
```

## Updating Dependencies Safely
```bash
# Check for outdated packages
pip list --outdated

# Check for security vulnerabilities
pip-audit

# Update a specific package
pip install --upgrade fastapi
pip freeze > requirements.txt

# Test after updating
pytest tests/ -v
```

## Virtual Environment Management
```bash
# Create (always at project root)
python -m venv .venv

# Activate
source .venv/bin/activate      # Linux/Mac
.venv\Scripts\activate         # Windows

# Deactivate
deactivate

# Recreate from scratch
rm -rf .venv
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Docker Packaging
```dockerfile
# See docker/dockerfile-patterns.md for full pattern
# Key points for Python:

# Use slim, not alpine (avoid musl/glibc issues)
FROM python:3.12-slim-bookworm

# Install deps first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy code
COPY . .

# Non-root user
USER appuser

# Production server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

## .env.example
```bash
# Application
ENVIRONMENT=dev
DEBUG=true
APP_NAME=myapp

# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/myapp

# Redis
REDIS_URL=redis://localhost:6379/0

# Auth
JWT_SECRET=change-me-in-production
JWT_EXPIRY_MINUTES=60

# CORS
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```
