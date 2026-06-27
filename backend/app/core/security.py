"""认证与安全工具"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _utcnow() -> datetime:
    """返回 UTC 当前时间（兼容 Python 3.11+）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = _utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = _utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return {}


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从 JWT 获取当前登录用户"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = decode_token(token)
    user_id_str = payload.get("sub")
    if user_id_str is None or payload.get("type") != "access":
        raise credentials_exception
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    if user.is_locked and user.locked_until and user.locked_until > _utcnow():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="账号已锁定")
    return user


async def get_current_user_optional(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """从 JWT 获取当前用户，未登录则返回 None（不报错）"""
    if not token:
        return None
    payload = decode_token(token)
    user_id_str = payload.get("sub")
    if user_id_str is None or payload.get("type") != "access":
        return None
    try:
        user_id = int(user_id_str)
    except (TypeError, ValueError):
        return None
    return db.query(User).filter(User.id == user_id).first()


async def get_current_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """要求管理员权限"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


async def get_current_premium_user(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """要求会员权限（管理员等同终身会员，无试用期逻辑）"""
    if current_user.role == "admin":
        return current_user  # 管理员等同终身会员
    if current_user.role != "premium":
        raise HTTPException(
            status_code=402,  # Payment Required
            detail="该功能需要会员权限，请先升级",
        )
    if current_user.subscription_expires_at and current_user.subscription_expires_at < _utcnow():
        raise HTTPException(
            status_code=402,
            detail="会员已过期，请续费",
        )
    return current_user


async def get_current_premium_optional(
    current_user: User = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """获取会员用户（可选）：管理员或有效订阅会员返回用户，否则返回 None"""
    if current_user is None:
        return None
    if current_user.role == "admin":
        return current_user
    if current_user.role != "premium":
        return None
    if current_user.subscription_expires_at and current_user.subscription_expires_at < _utcnow():
        return None
    return current_user
