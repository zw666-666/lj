"""用户模型"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone = Column(String(20), unique=True)
    email = Column(String(255), unique=True)
    password_hash = Column(String(255), nullable=True)  # OAuth 用户无密码
    oauth_provider = Column(String(20), nullable=True)   # "alipay"
    oauth_id = Column(String(64), unique=True, nullable=True)  # 支付宝 user_id
    nickname = Column(String(100))
    avatar_url = Column(String(500))
    license_no = Column(String(50))
    law_firm = Column(String(200))
    expertise = Column(Text)
    role = Column(String(20), default="normal")  # normal / premium / admin
    subscription_expires_at = Column(DateTime)  # 订阅到期时间
    lifetime_export_count = Column(Integer, default=0)  # 终身导出次数
    is_locked = Column(Boolean, default=False)
    login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    search_count = Column(Integer, default=0)
    read_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    token = Column(String(500), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
