# Python Skill

## Purpose
Python development patterns for building production-ready backend services, APIs, scripts, and automation.

## When to Activate
- Writing any Python code (APIs, scripts, jobs, workers)
- Setting up a new Python project
- Debugging Python applications
- Writing tests
- Managing dependencies and packaging

## Sub-Skills
| File | When to Read |
|------|-------------|
| `project-structure.md` | Setting up a new Python project |
| `fastapi-patterns.md` | Building REST APIs with FastAPI |
| `testing.md` | Writing tests (unit, integration, e2e) |
| `packaging.md` | Dependencies, virtual envs, Docker packaging |

## Also Read
- `security/web-security.md` — Input validation, auth, CORS
- `security/auth-and-secrets.md` — Secret management in Python
- `docker/dockerfile-patterns.md` — Python Dockerfile patterns
- `kibana/SKILL.md` — Structured logging setup

## Core Python Rules
1. **Always use virtual environments** — never install into system Python
2. **Always pin dependencies** — `requirements.txt` with exact versions
3. **Always use type hints** — for all function signatures
4. **Always use Pydantic** — for data validation and settings
5. **Always use async** — for I/O-bound operations (FastAPI, DB, HTTP calls)
6. **Always use structured logging** — structlog or python-json-logger
7. **Always handle errors** — specific exceptions, not bare `except:`
8. **Always write tests** — pytest with minimum 80% coverage target
9. **Always use linting** — ruff for formatting + linting
10. **Always use .env for config** — never hardcode settings

## Python Version
```
Default: Python 3.12 (latest stable)
Minimum: Python 3.11
Use pyenv for version management
```

## Quick Project Setup
```bash
# Create project
mkdir myapp && cd myapp
python -m venv .venv
source .venv/bin/activate

# Install core dependencies
pip install fastapi uvicorn[standard] pydantic-settings sqlalchemy asyncpg
pip install structlog python-dotenv redis
pip install ruff pytest pytest-asyncio pytest-cov httpx  # Dev deps

# Freeze deps
pip freeze > requirements.txt

# Create structure
mkdir -p backend/{api,models,services,core} tests
touch backend/__init__.py backend/main.py backend/core/config.py
```

## Coding Standards
```python
# Use ruff for everything
# pyproject.toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM", "ASYNC"]

[tool.ruff.format]
quote-style = "double"

# Run linting
ruff check .
ruff check . --fix
ruff format .
```

## Essential Commands
```bash
# Virtual environment
python -m venv .venv
source .venv/bin/activate       # Linux/Mac
.venv\Scripts\activate          # Windows

# Dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip freeze > requirements.txt
pip audit                        # Security check

# Running
uvicorn backend.main:app --reload --port 8000

# Testing
pytest tests/ -v --cov=backend --cov-report=term-missing

# Linting
ruff check . && ruff format --check .

# Type checking
mypy backend/ --ignore-missing-imports
```
