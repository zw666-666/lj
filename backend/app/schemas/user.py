"""用户相关 Pydantic Schema"""
import re
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


class UserRegisterRequest(BaseModel):
    phone: Optional[str] = None
    email: Optional[str] = None
    password: str = Field(..., min_length=8, max_length=64)
    nickname: Optional[str] = None
    sms_code: Optional[str] = None
    bind_phone: bool = False

    @model_validator(mode="after")
    def validate_contact(self):
        """确保至少填写手机号或邮箱，且密码和手机号格式符合规范"""
        # 空字符串归一化为 None
        if not self.phone:
            self.phone = None
        if not self.email:
            self.email = None
        # 至少填写一项
        if not self.phone and not self.email:
            raise ValueError("手机号或邮箱至少填写一项")
        # 手机号格式（仅当填写时校验）
        if self.phone and not re.match(r"^1[3-9]\d{9}$", self.phone):
            raise ValueError("手机号格式不正确（11位，1开头）")
        # 密码规范
        if not (any(c.isalpha() for c in self.password) and any(c.isdigit() for c in self.password)):
            raise ValueError("密码必须包含字母和数字")
        return self


class LoginRequest(BaseModel):
    account: str = Field(..., description="手机号或邮箱")
    password: Optional[str] = None
    sms_code: Optional[str] = None
    login_type: str = Field(default="password", description="password / sms_code")

    @model_validator(mode="after")
    def validate_login(self):
        if self.login_type not in {"password", "sms_code"}:
            raise ValueError("login_type 仅支持 password 或 sms_code")
        if self.login_type == "password" and not self.password:
            raise ValueError("密码不能为空")
        if self.login_type == "sms_code" and not self.sms_code:
            raise ValueError("验证码不能为空")
        return self


class SmsCodeRequest(BaseModel):
    phone: str
    scene: str = Field(default="login", description="register / login / bind")

    @model_validator(mode="after")
    def validate_scene(self):
        if self.scene not in {"register", "login", "bind"}:
            raise ValueError("scene 仅支持 register / login / bind")
        return self


class SmsCodeResponse(BaseModel):
    expires_in: int
    cooldown_seconds: int
    mock_code: Optional[str] = None


class PhoneBindRequest(BaseModel):
    phone: str
    sms_code: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    need_setup: bool = False  # 短信验证码登录时，若用户是新注册或无密码，需引导设置密码和用户名


class UserSetupRequest(BaseModel):
    """短信注册后首次设置密码和用户名"""
    password: str = Field(..., min_length=8, max_length=64)
    nickname: str = Field(..., min_length=2, max_length=20)

    @model_validator(mode="after")
    def validate_password(self):
        if not (any(c.isalpha() for c in self.password) and any(c.isdigit() for c in self.password)):
            raise ValueError("密码必须包含字母和数字")
        return self


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserProfileResponse(BaseModel):
    id: int
    phone: Optional[str]
    email: Optional[str]
    nickname: Optional[str]
    avatar_url: Optional[str]
    license_no: Optional[str]
    law_firm: Optional[str]
    expertise: Optional[str]
    role: str
    subscription_expires_at: Optional[datetime] = None
    subscription_status: str = "free"  # free / premium / expired
    lifetime_export_count: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    license_no: Optional[str] = None
    law_firm: Optional[str] = None
    expertise: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=64)

    @model_validator(mode="after")
    def validate_password(self):
        if not (any(c.isalpha() for c in self.new_password) and any(c.isdigit() for c in self.new_password)):
            raise ValueError("Password must contain letters and digits")
        return self


class UserStatsResponse(BaseModel):
    search_count: int = 0
    read_count: int = 0
    favorite_count: int = 0
    note_count: int = 0
