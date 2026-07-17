# FastAPI Patterns

## Error Handling
```python
# backend/core/exceptions.py
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400, detail: dict = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail or {}

class NotFoundError(AppException):
    def __init__(self, resource: str, id: str | int):
        super().__init__(
            message=f"{resource} not found",
            status_code=404,
            detail={"resource": resource, "id": str(id)}
        )

class ConflictError(AppException):
    def __init__(self, message: str):
        super().__init__(message=message, status_code=409)

# Register in main.py
@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.message,
            "detail": exc.detail,
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"}
    )
```

## Dependency Injection Pattern
```python
# backend/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from backend.core.config import settings
from backend.core.database import get_db
from backend.services.user_service import UserService

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
):
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    service = UserService(db)
    user = await service.get_by_id(int(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

async def require_admin(current_user = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
```

## Background Tasks
```python
from fastapi import BackgroundTasks

@router.post("/send-notification")
async def send_notification(
    user_id: int,
    message: str,
    background_tasks: BackgroundTasks,
):
    # Return immediately, process in background
    background_tasks.add_task(send_email_notification, user_id, message)
    return {"status": "notification_queued"}

async def send_email_notification(user_id: int, message: str):
    # This runs after the response is sent
    logger.info("sending_notification", user_id=user_id)
    # ... send email logic ...
```

## File Upload Pattern
```python
from fastapi import UploadFile, File

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user),
):
    # Validate file
    allowed_types = {"image/jpeg", "image/png", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(400, f"File type {file.content_type} not allowed")
    
    max_size = 10 * 1024 * 1024  # 10MB
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(400, "File too large (max 10MB)")
    
    # Save to S3 or local storage
    file_path = await storage.save(content, file.filename, current_user.id)
    
    return {"file_path": file_path, "size": len(content)}
```

## WebSocket Pattern
```python
from fastapi import WebSocket, WebSocketDisconnect

class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active.pop(user_id, None)

    async def send_to_user(self, user_id: str, data: dict):
        ws = self.active.get(user_id)
        if ws:
            await ws.send_json(data)

manager = ConnectionManager()

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            # Process incoming message
            await manager.send_to_user(user_id, {"echo": data})
    except WebSocketDisconnect:
        manager.disconnect(user_id)
```

## Service Layer Pattern
```python
# backend/services/user_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from backend.models.user import User
from backend.schemas.user import UserCreate
from backend.core.security import hash_password
from backend.core.exceptions import NotFoundError, ConflictError

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: UserCreate) -> User:
        # Check for existing
        existing = await self.get_by_email(data.email)
        if existing:
            raise ConflictError(f"Email {data.email} already registered")

        user = User(
            email=data.email,
            name=data.name,
            password_hash=hash_password(data.password),
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def get_by_id(self, user_id: int) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User", user_id)
        return user

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list(self, page: int = 1, per_page: int = 20) -> tuple[list[User], int]:
        offset = (page - 1) * per_page
        
        result = await self.db.execute(
            select(User).offset(offset).limit(per_page).order_by(User.created_at.desc())
        )
        users = list(result.scalars().all())
        
        count_result = await self.db.execute(select(func.count(User.id)))
        total = count_result.scalar()
        
        return users, total
```

## Database Migration (Alembic)
```bash
# Setup
pip install alembic
alembic init alembic

# Edit alembic/env.py to use your models and async engine
# Then:
alembic revision --autogenerate -m "create users table"
alembic upgrade head
alembic downgrade -1
alembic history
```
