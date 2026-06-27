"""认证接口：注册、登录、刷新 Token"""
from datetime import timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    _utcnow,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.user import RefreshToken, User
from app.schemas.user import (
    LoginRequest,
    PhoneBindRequest,
    RefreshTokenRequest,
    SmsCodeRequest,
    SmsCodeResponse,
    TokenResponse,
    UserProfileResponse,
    UserRegisterRequest,
    UserSetupRequest,
)
from app.services.sms_service import SmsService

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/sms/send-code", response_model=SmsCodeResponse)
def send_sms_code(req: SmsCodeRequest):
    """发送短信验证码"""
    result = SmsService.send_code(req.scene, req.phone)
    return SmsCodeResponse(
        expires_in=result.expires_in,
        cooldown_seconds=result.cooldown_seconds,
        mock_code=result.mock_code,
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    if req.phone and db.query(User).filter(User.phone == req.phone).first():
        raise HTTPException(status_code=400, detail="手机号已被注册")
    if req.email and db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    phone = None
    if req.bind_phone:
        if not req.phone:
            raise HTTPException(status_code=400, detail="绑定手机号时必须填写手机号")
        if not req.sms_code:
            raise HTTPException(status_code=400, detail="绑定手机号时必须填写验证码")
        phone = SmsService.validate_phone(req.phone)
        SmsService.verify_code("register", phone, req.sms_code)
    elif req.phone:
        phone = SmsService.validate_phone(req.phone)

    nickname = (req.nickname or "").strip()
    if not nickname:
        raise HTTPException(status_code=400, detail="用户名为必填项")
    if db.query(User).filter(User.nickname == nickname).first():
        raise HTTPException(status_code=400, detail="该用户名已被使用")

    user = User(
        phone=phone,
        email=req.email,
        password_hash=hash_password(req.password),
        nickname=nickname,
    )
    db.add(user)
    db.flush()

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token_str = create_refresh_token({"sub": str(user.id), "jti": str(uuid.uuid4())})

    rt = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=_utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录"""
    user = None

    need_setup = False

    if req.login_type == "sms_code":
        phone = SmsService.validate_phone(req.account)
        SmsService.verify_code("login", phone, req.sms_code or "")
        user = db.query(User).filter(User.phone == phone).first()
        if not user:
            # 手机号未注册 → 自动创建账号（空密码，需引导设置）
            user = User(
                phone=phone,
                password_hash="",  # 空字符串占位（数据库NOT NULL约束），setup 后替换为真实 hash
                nickname=f"用户{phone[-4:]}",  # 临时昵称
            )
            db.add(user)
            db.flush()
            need_setup = True
        elif not user.password_hash:
            # 已有账号但未设置密码（之前通过短信注册但未完成设置）
            need_setup = True
    else:
        if "@" in req.account:
            user = db.query(User).filter(User.email == req.account).first()
        else:
            user = db.query(User).filter(User.phone == req.account).first()

        if not user:
            raise HTTPException(status_code=401, detail="账号或密码错误")

        if user.is_locked and user.locked_until and user.locked_until > _utcnow():
            raise HTTPException(status_code=403, detail="账号已锁定，请稍后重试")

        if not verify_password(req.password or "", user.password_hash or ""):
            user.login_attempts = (user.login_attempts or 0) + 1
            if user.login_attempts >= 5:
                user.is_locked = True
                user.locked_until = _utcnow() + timedelta(minutes=15)
            db.commit()
            raise HTTPException(status_code=401, detail="账号或密码错误")

        user.login_attempts = 0
        user.is_locked = False

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token_str = create_refresh_token({"sub": str(user.id), "jti": str(uuid.uuid4())})

    rt = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=_utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token_str,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        need_setup=need_setup,
    )


@router.post("/phone/bind")
def bind_phone(
    req: PhoneBindRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """登录后绑定手机号"""
    phone = SmsService.validate_phone(req.phone)
    if db.query(User).filter(User.phone == phone, User.id != current_user.id).first():
        raise HTTPException(status_code=400, detail="该手机号已被其他账号绑定")

    SmsService.verify_code("bind", phone, req.sms_code)
    current_user.phone = phone
    db.commit()
    db.refresh(current_user)
    return {"message": "手机号绑定成功", "phone": current_user.phone}


@router.post("/phone/unbind")
def unbind_phone(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """解绑手机号"""
    if not current_user.phone:
        raise HTTPException(status_code=400, detail="当前账号未绑定手机号")
    if not current_user.password_hash and not current_user.email:
        raise HTTPException(status_code=400, detail="解绑前请先设置密码或绑定邮箱，否则将无法登录")
    phone = current_user.phone
    current_user.phone = None
    db.commit()
    return {"message": "手机号已解绑", "phone": phone}


@router.post("/setup")
def setup_account(
    req: UserSetupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """短信注册后首次设置密码和用户名"""
    if current_user.password_hash:
        raise HTTPException(status_code=400, detail="密码已设置，无需重复操作")

    # 检查用户名是否被占用
    existing = db.query(User).filter(User.nickname == req.nickname, User.id != current_user.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="该用户名已被使用")

    current_user.password_hash = hash_password(req.password)
    current_user.nickname = req.nickname
    db.commit()
    db.refresh(current_user)

    return {
        "message": "设置成功",
        "nickname": current_user.nickname,
        "phone": current_user.phone,
    }


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(req: RefreshTokenRequest, db: Session = Depends(get_db)):
    """刷新 Access Token"""
    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="无效的 Refresh Token")

    token_record = db.query(RefreshToken).filter(
        RefreshToken.token == req.refresh_token,
        RefreshToken.revoked == False,
    ).first()
    if not token_record or token_record.expires_at < _utcnow():
        raise HTTPException(status_code=401, detail="Refresh Token 已过期")

    token_record.revoked = True

    user_id = payload["sub"]
    new_access = create_access_token({"sub": str(user_id)})
    new_refresh_str = create_refresh_token({"sub": str(user_id), "jti": str(uuid.uuid4())})

    new_rt = RefreshToken(
        user_id=user_id,
        token=new_refresh_str,
        expires_at=_utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(new_rt)
    db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh_str,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/me", response_model=UserProfileResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    subscription_status = "free"
    if current_user.role == "admin":
        subscription_status = "premium"
    elif current_user.role == "premium":
        if current_user.subscription_expires_at and current_user.subscription_expires_at < _utcnow():
            subscription_status = "expired"
        else:
            subscription_status = "premium"

    return UserProfileResponse(
        id=current_user.id,
        phone=current_user.phone,
        email=current_user.email,
        nickname=current_user.nickname,
        avatar_url=current_user.avatar_url,
        license_no=current_user.license_no,
        law_firm=current_user.law_firm,
        expertise=current_user.expertise,
        role=current_user.role,
        subscription_expires_at=current_user.subscription_expires_at,
        subscription_status=subscription_status,
        lifetime_export_count=current_user.lifetime_export_count or 0,
        created_at=current_user.created_at,
    )
