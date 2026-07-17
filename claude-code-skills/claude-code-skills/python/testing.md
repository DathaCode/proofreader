# Python Testing

## Test Structure
```
tests/
├── conftest.py              # Shared fixtures (db, client, users)
├── test_api/                # API endpoint tests (integration)
│   ├── conftest.py
│   ├── test_auth.py
│   └── test_users.py
├── test_services/           # Service layer tests (unit)
│   └── test_user_service.py
└── test_integration/        # Full integration tests
    └── test_db.py
```

## conftest.py (Shared Fixtures)
```python
# tests/conftest.py
import pytest
import asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from backend.main import app
from backend.core.database import get_db
from backend.models.base import Base

TEST_DATABASE_URL = "postgresql+asyncpg://test:test@localhost:5432/myapp_test"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
async def db(engine):
    session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session() as s:
        yield s
        await s.rollback()

@pytest.fixture
async def client(db):
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture
async def authenticated_client(client, db):
    """Client with auth token for protected endpoints."""
    from backend.services.user_service import UserService
    from backend.schemas.user import UserCreate
    from backend.core.security import create_access_token

    service = UserService(db)
    user = await service.create(UserCreate(
        email="test@example.com",
        name="Test User",
        password="testpassword123"
    ))
    await db.commit()

    token = create_access_token({"sub": str(user.id)})
    client.headers["Authorization"] = f"Bearer {token}"
    yield client, user
```

## API Test Examples
```python
# tests/test_api/test_users.py
import pytest

class TestUserEndpoints:
    @pytest.mark.asyncio
    async def test_create_user(self, client):
        response = await client.post("/api/v1/users/", json={
            "email": "new@example.com",
            "name": "New User",
            "password": "securepassword123"
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["name"] == "New User"
        assert "password" not in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(self, client):
        user_data = {
            "email": "dup@example.com",
            "name": "User",
            "password": "password123"
        }
        await client.post("/api/v1/users/", json=user_data)
        response = await client.post("/api/v1/users/", json=user_data)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_user_invalid_email(self, client):
        response = await client.post("/api/v1/users/", json={
            "email": "not-an-email",
            "name": "User",
            "password": "password123"
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_current_user(self, authenticated_client):
        client, user = authenticated_client
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 200
        assert response.json()["email"] == user.email

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client):
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 403  # or 401
```

## Service Test Examples
```python
# tests/test_services/test_user_service.py
import pytest
from backend.services.user_service import UserService
from backend.schemas.user import UserCreate
from backend.core.exceptions import NotFoundError, ConflictError

class TestUserService:
    @pytest.mark.asyncio
    async def test_create_user(self, db):
        service = UserService(db)
        user = await service.create(UserCreate(
            email="svc@example.com",
            name="Service Test",
            password="password123"
        ))
        assert user.id is not None
        assert user.email == "svc@example.com"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db):
        service = UserService(db)
        with pytest.raises(NotFoundError):
            await service.get_by_id(99999)

    @pytest.mark.asyncio
    async def test_list_users_pagination(self, db):
        service = UserService(db)
        # Create 5 users
        for i in range(5):
            await service.create(UserCreate(
                email=f"page{i}@example.com",
                name=f"User {i}",
                password="password123"
            ))
        await db.flush()

        users, total = await service.list(page=1, per_page=2)
        assert len(users) == 2
        assert total == 5
```

## Running Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=backend --cov-report=term-missing --cov-report=html

# Run specific test file
pytest tests/test_api/test_users.py

# Run specific test
pytest tests/test_api/test_users.py::TestUserEndpoints::test_create_user

# Run with verbose output
pytest -v --tb=long

# Run only failed tests from last run
pytest --lf

# Run tests matching a keyword
pytest -k "user and not delete"
```

## Test Best Practices
```
1. Test behavior, not implementation — test what the API returns, not internal method calls
2. Each test should be independent — use fixtures, don't depend on test order
3. Use descriptive test names — test_create_user_with_duplicate_email_returns_409
4. Test edge cases — empty input, max length, special characters, null values
5. Test error paths — unauthorized, not found, validation errors, server errors
6. Use factories for test data — don't repeat user creation in every test
7. Keep tests fast — mock external services, use test database
8. Aim for 80%+ coverage — but don't write useless tests just for coverage
```
