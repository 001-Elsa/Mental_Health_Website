from datetime import datetime, timedelta
from uuid import uuid4
from typing import Annotated
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import get_settings
from backend.core.time import utc_now
from database.database import get_async_db, get_sync_db
from database.models import User

ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# 模拟验证码存储（生产环境用 Redis）
pending_codes: dict[str, str] = {}


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = utc_now() + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire, "type": "access", "jti": uuid4().hex})
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(*, user_id: int, token_version: int) -> tuple[str, datetime]:
    settings = get_settings()
    expires_at = utc_now() + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "user_id": user_id,
        "ver": token_version,
        "type": "refresh",
        "jti": uuid4().hex,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), expires_at


def create_websocket_token(*, user_id: int, token_version: int) -> str:
    payload = {
        "user_id": user_id,
        "ver": token_version,
        "type": "websocket",
        "jti": uuid4().hex,
        "exp": utc_now() + timedelta(seconds=60),
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except JWTError:
        return None


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_sync_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("user_id") if payload and payload.get("type") == "access" else None
    if not user_id:
        raise HTTPException(status_code=401, detail="登录状态已失效")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or int(payload.get("ver", -1)) != user.token_version:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


async def get_current_user_async(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: AsyncSession = Depends(get_async_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("user_id") if payload and payload.get("type") == "access" else None
    if not user_id:
        raise HTTPException(status_code=401, detail="登录状态已失效")
    user = (await db.execute(select(User).where(User.id == int(user_id)))).scalar_one_or_none()
    if not user or int(payload.get("ver", -1)) != user.token_version:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def get_optional_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Session = Depends(get_sync_db),
) -> User | None:
    if not credentials:
        return None
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("user_id") if payload and payload.get("type") == "access" else None
    if not user_id:
        return None
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or int(payload.get("ver", -1)) != user.token_version:
        return None
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
