# Python Project Structure

## Standard FastAPI Project Layout
```
myapp/
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app creation and startup
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Settings (from env vars via Pydantic)
│   │   ├── database.py         # DB engine, session factory
│   │   ├── security.py         # Auth helpers, JWT, hashing
│   │   └── logging.py          # Structured logging setup
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py           # Main router that includes all sub-routers
│   │   ├── deps.py             # Shared dependencies (get_db, get_current_user)
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── users.py        # User endpoints
│   │       ├── auth.py         # Auth endpoints
│   │       └── items.py        # Business endpoints
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py             # SQLAlchemy Base
│   │   ├── user.py             # User ORM model
│   │   └── item.py             # Item ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py             # User Pydantic schemas (request/response)
│   │   └── item.py             # Item Pydantic schemas
│   ├── services/
│   │   ├── __init__.py
│   │   ├── user_service.py     # User business logic
│   │   └── item_service.py     # Item business logic
│   ├── repositories/
│   │   ├── __init__.py
│   │   ├── user_repo.py        # User DB queries
│   │   └── item_repo.py        # Item DB queries
│   └── jobs/
│       ├── __init__.py
│       └── cleanup.py          # Background/cron jobs
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Shared fixtures
│   ├── test_api/
│   │   ├── test_users.py
│   │   └── test_auth.py
│   ├── test_services/
│   │   └── test_user_service.py
│   └── test_integration/
│       └── test_db.py
│
├── alembic/                     # Database migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│
├── scripts/
│   ├── seed_db.py              # Seed data for development
│   └── migrate.sh              # Migration helper
│
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml               # Project metadata + tool config
├── requirements.txt             # Production deps (pinned)
├── requirements-dev.txt         # Dev deps (testing, linting)
└── README.md
```

## Core Config Pattern
```python
# backend/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "myapp"
    ENVIRONMENT: str = "dev"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/myapp"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Auth
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60
    
    # CORS
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

## Main App Pattern
```python
# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from backend.core.config import settings
from backend.core.database import engine
from backend.core.logging import setup_logging
from backend.api.router import api_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    setup_logging()
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT != "prod" else None,
    redoc_url=None,
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.get("/health")
async def health():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}
```

## Database Pattern (Async SQLAlchemy)
```python
# backend/core/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from backend.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    echo=settings.DEBUG,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
```

## API Endpoint Pattern
```python
# backend/api/v1/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_db
from backend.api.deps import get_current_user
from backend.schemas.user import UserCreate, UserResponse, UserList
from backend.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])

@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    user = await service.create(user_in)
    return user

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user = Depends(get_current_user),
):
    return current_user

@router.get("/", response_model=UserList)
async def list_users(
    page: int = 1,
    per_page: int = 20,
    db: AsyncSession = Depends(get_db),
    _current_user = Depends(get_current_user),
):
    service = UserService(db)
    users, total = await service.list(page=page, per_page=per_page)
    return UserList(data=users, total=total, page=page, per_page=per_page)
```

## Pydantic Schema Pattern
```python
# backend/schemas/user.py
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)

class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}

class UserList(BaseModel):
    data: list[UserResponse]
    total: int
    page: int
    per_page: int
```

## pyproject.toml
```toml
[project]
name = "myapp"
version = "1.0.0"
requires-python = ">=3.12"

[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
ignore_missing_imports = true
```
