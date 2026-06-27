"""用户信息管理接口"""
from fastapi import APIRouter, Depends, Query
from app.core.security import get_current_user
from app.models.user import User, RefreshToken
from app.schemas.user import UserProfileUpdate, UserStatsResponse, UserProfileResponse, PasswordChangeRequest
from app.core.database import get_db
from sqlalchemy.orm import Session
from sqlalchemy import desc

router = APIRouter(prefix="/api/user", tags=["用户"])


@router.put("/profile", response_model=UserProfileResponse)
def update_profile(
    req: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新个人信息（昵称、密码、头像等）"""
    data = req.model_dump(exclude_unset=True)

    # 昵称唯一性检查
    if "nickname" in data and data["nickname"]:
        existing = db.query(User).filter(
            User.nickname == data["nickname"], User.id != current_user.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="该昵称已被使用")

    for field, value in data.items():
        setattr(current_user, field, value)
    db.commit()
    db.refresh(current_user)

    # 计算订阅状态
    subscription_status = "free"
    if current_user.role == "admin":
        subscription_status = "premium"
    elif current_user.role == "premium":
        from app.core.security import _utcnow
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


@router.put("/password")
def change_password(
    req: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改密码（需验证原密码）"""
    from app.core.security import verify_password, hash_password
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"message": "密码已修改"}


@router.get("/stats", response_model=UserStatsResponse)
def get_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取个人使用统计"""
    from app.models.user_content import Favorite, Note
    favorite_count = db.query(Favorite).filter(Favorite.user_id == current_user.id).count()
    note_count = db.query(Note).filter(Note.user_id == current_user.id).count()
    return UserStatsResponse(
        search_count=current_user.search_count or 0,
        read_count=current_user.read_count or 0,
        favorite_count=favorite_count,
        note_count=note_count,
    )


@router.get("/search-history")
def get_search_history(
    limit: int = Query(default=30, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取检索历史（按时间倒序，去重相同内容）"""
    from app.models.user_content import UserActivity
    activities = (
        db.query(UserActivity)
        .filter(UserActivity.user_id == current_user.id, UserActivity.activity_type == "search")
        .order_by(desc(UserActivity.created_at))
        .limit(limit * 2)
        .all()
    )
    # 去重：相同关键词只保留最新一次
    seen = set()
    result = []
    for a in activities:
        key = (a.detail or "").strip()
        if key and key not in seen:
            seen.add(key)
            result.append({
                "id": a.id,
                "detail": a.detail,
                "result_data": a.result_data or {"total": 0, "cases": []},
                "created_at": str(a.created_at),
            })
        if len(result) >= limit:
            break
    return result


@router.delete("/search-history")
def clear_search_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """清空检索历史"""
    from app.models.user_content import UserActivity
    deleted = db.query(UserActivity).filter(
        UserActivity.user_id == current_user.id,
        UserActivity.activity_type == "search",
    ).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.delete("/account")
def delete_account(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """注销当前账号，清除所有个人数据"""
    from app.models.user_content import Favorite, Note, CaseGroup, CaseGroupItem, QASession, QAMessage, UserActivity, Notification
    # 先删子表（没有 user_id 的关联表）
    user_groups = db.query(CaseGroup).filter(CaseGroup.user_id == current_user.id).all()
    for g in user_groups:
        db.query(CaseGroupItem).filter(CaseGroupItem.group_id == g.id).delete()
    user_sessions = db.query(QASession).filter(QASession.user_id == current_user.id).all()
    for s in user_sessions:
        db.query(QAMessage).filter(QAMessage.session_id == s.id).delete()
    # 清除有 user_id 的个人数据
    for model in [Favorite, Note, CaseGroup, QASession, UserActivity, Notification]:
        db.query(model).filter(model.user_id == current_user.id).delete()
    # 清除 refresh tokens
    db.query(RefreshToken).filter(RefreshToken.user_id == current_user.id).delete()
    # 清除订阅和订单
    from app.models.subscription import Subscription, PaymentOrder
    db.query(Subscription).filter(Subscription.user_id == current_user.id).delete()
    db.query(PaymentOrder).filter(PaymentOrder.user_id == current_user.id).delete()
    # 清除每日用量
    from app.models.usage import UsageDaily
    db.query(UsageDaily).filter(UsageDaily.user_id == current_user.id).delete()
    # 最后删用户
    db.delete(current_user)
    db.commit()
    return {"message": "账号已注销"}


@router.get("/read-history")
def get_read_history(
    limit: int = Query(default=30, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取阅读历史（按时间倒序，去重相同案例）"""
    from app.models.user_content import UserActivity
    from app.models.case import Case
    activities = (
        db.query(UserActivity)
        .filter(UserActivity.user_id == current_user.id, UserActivity.activity_type == "read")
        .order_by(desc(UserActivity.created_at))
        .limit(limit * 2)
        .all()
    )
    # 去重：相同案例只保留最新一次
    seen = set()
    result = []
    for a in activities:
        if a.case_id and a.case_id not in seen:
            seen.add(a.case_id)
            # 获取最新案例标题
            case = db.query(Case).filter(Case.id == a.case_id).first()
            result.append({
                "id": a.id,
                "case_id": a.case_id,
                "title": (case.title or case.case_no) if case else a.detail,
                "case_no": case.case_no if case else "",
                "detail": a.detail,
                "created_at": str(a.created_at),
            })
        if len(result) >= limit:
            break
    return result
