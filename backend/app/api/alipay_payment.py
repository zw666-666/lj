"""支付宝沙箱扫码支付（购买会员）—— 使用官方 SDK"""
import time
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from alipay import AliPay

from app.core.database import get_db
from app.core.config import settings
from app.core.security import get_current_user, _utcnow
from app.models.user import User
from app.models.subscription import SubscriptionPlan, PaymentOrder, Subscription

router = APIRouter(prefix="/api/payment/alipay", tags=["支付宝支付"])

NOTIFY_URL = settings.ALIPAY_NOTIFY_URL or settings.ALIPAY_CALLBACK_URL.replace("callback", "notify")

# 内存缓存：仅用于异步通知快速查找订单（数据库才是真正的来源）
_pending_orders: dict[str, dict] = {}

# 缓存 AliPay 实例，避免每次请求重新解析 RSA 密钥
_alipay_instance: AliPay | None = None


def _get_alipay() -> AliPay:
    """获取（并缓存）AliPay 实例"""
    global _alipay_instance
    if _alipay_instance is not None:
        return _alipay_instance

    priv = settings.ALIPAY_PRIVATE_KEY
    pub = settings.ALIPAY_PUBLIC_KEY
    if "\\n" in priv:
        priv = priv.replace("\\n", "\n")
    if "\\n" in pub:
        pub = pub.replace("\\n", "\n")

    _alipay_instance = AliPay(
        appid=settings.ALIPAY_APP_ID,
        app_notify_url=NOTIFY_URL,
        app_private_key_string=priv,
        alipay_public_key_string=pub,
        sign_type="RSA2",
        debug=settings.ALIPAY_SANDBOX,
    )
    return _alipay_instance


def _upgrade_user(db: Session, user: User, plan: SubscriptionPlan, days: int) -> None:
    """升级用户为会员（在当前 db 会话中操作）"""
    now = _utcnow()
    if user.subscription_expires_at and user.subscription_expires_at > now:
        user.subscription_expires_at = user.subscription_expires_at + timedelta(days=days)
    else:
        user.subscription_expires_at = now + timedelta(days=days)
    user.role = "premium"

    # 创建订阅记录
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status="active",
        started_at=now,
        expires_at=user.subscription_expires_at,
    )
    db.add(sub)


@router.post("/create")
def create_payment(
    plan: str = "monthly",
    plan_id: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建支付订单——从数据库读取方案真实价格"""
    if not settings.ALIPAY_APP_ID:
        raise HTTPException(status_code=500, detail="未配置支付宝 AppID")

    # 从数据库查方案
    db_plan = None
    if plan_id:
        db_plan = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == plan_id,
            SubscriptionPlan.is_active == True,
        ).first()
    if not db_plan:
        db_plan = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.plan_type == plan,
            SubscriptionPlan.is_active == True,
        ).first()
    if not db_plan:
        raise HTTPException(status_code=400, detail="未找到对应会员方案")

    amount_yuan = f"{(db_plan.price_cents / 100):.2f}"

    # 调用支付宝预下单接口（带重试，沙箱网关偶发不稳定）
    # 关键：每次重试生成新的 out_trade_no，避免订单号冲突导致支付宝返回错误
    alipay = _get_alipay()
    last_err = ""
    for attempt in range(3):
        out_trade_no = f"LJVIP{datetime.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6]}"
        try:
            result = alipay.api_alipay_trade_precreate(
                subject=f"律镜 {db_plan.name}",
                out_trade_no=out_trade_no,
                total_amount=amount_yuan,
            )
            if result.get("code") == "10000":
                # 成功：入库 + 写入内存缓存
                order = PaymentOrder(
                    user_id=current_user.id,
                    plan_id=db_plan.id,
                    order_no=out_trade_no,
                    amount_cents=db_plan.price_cents,
                    status="pending",
                    payment_method="alipay",
                )
                db.add(order)
                db.commit()
                _pending_orders[out_trade_no] = {
                    "user_id": current_user.id,
                    "plan_id": db_plan.id,
                    "plan_type": db_plan.plan_type,
                    "days": 365 if db_plan.plan_type == "yearly" else 30,
                }
                return {
                    "qr_code": result.get("qr_code", ""),
                    "out_trade_no": out_trade_no,
                    "amount": amount_yuan,
                    "plan_name": db_plan.name,
                    "plan_type": db_plan.plan_type,
                }
            # 业务错误码不重试（除系统错误外）
            msg = result.get("sub_msg") or result.get("msg") or "创建支付失败"
            sub_code = result.get("sub_code") or ""
            # ACQ.SYSTEM_ERROR 等系统错误可重试（用新订单号）
            if sub_code in ("ACQ.SYSTEM_ERROR", "ACQ.MOBILE_PAYMENT_UNAVAILABLE") and attempt < 2:
                last_err = msg
                time.sleep(0.5)
                continue
            raise HTTPException(status_code=400, detail=msg)
        except HTTPException:
            raise
        except Exception as e:
            last_err = str(e)[:200]
            if attempt < 2:
                time.sleep(0.5)
                continue
            raise HTTPException(status_code=400, detail=f"创建支付失败: {last_err}")

    raise HTTPException(status_code=400, detail=f"创建支付失败: {last_err}")


@router.get("/status")
def check_payment(out_trade_no: str = "", current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """轮询支付状态

    修复：不再依赖内存 _pending_orders。
    1) 查 DB 订单是否已 paid（异步通知先到达时已写入）
    2) 否则查询支付宝 API（这是真实数据来源）
    3) 查到 TRADE_SUCCESS 时升级用户并更新订单状态
    """
    if not out_trade_no:
        return {"paid": False, "detail": "缺少订单号"}

    # 1) 查 DB 订单（out_trade_no 全局唯一，无需再限 user_id）
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == out_trade_no,
    ).first()
    if not order:
        return {"paid": False, "detail": "订单不存在"}
    if order.status == "paid":
        return {"paid": True, "detail": "支付成功"}

    # 2) 查询支付宝 API（订单还 pending，主动核实）
    try:
        alipay = _get_alipay()
        result = alipay.api_alipay_trade_query(out_trade_no=out_trade_no)
    except Exception as e:
        return {"paid": False, "detail": f"查询异常: {str(e)[:100]}"}

    if result.get("code") == "10000" and result.get("trade_status") in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        # 3) 升级用户 + 更新订单
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == order.plan_id).first()
        if plan:
            days = 365 if plan.plan_type == "yearly" else 30
            user = db.query(User).filter(User.id == order.user_id).first()
            if user and user.role != "premium":
                _upgrade_user(db, user, plan, days)
            order.status = "paid"
            order.alipay_trade_no = result.get("trade_no", "")
            order.paid_at = _utcnow()
            db.commit()
        # 清理内存缓存
        _pending_orders.pop(out_trade_no, None)
        return {"paid": True, "detail": "支付成功"}

    if result.get("trade_status") == "TRADE_CLOSED":
        # 用户在支付宝端取消了支付
        if order.status == "pending":
            order.status = "expired"
            db.commit()
        _pending_orders.pop(out_trade_no, None)
        return {"paid": False, "detail": "支付已取消"}

    return {"paid": False, "detail": result.get("msg", "等待支付")}


@router.post("/notify")
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    """支付宝异步通知"""
    body = await request.body()
    data = dict()
    for pair in body.decode().split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            data[k] = v

    # SDK 验签
    sign = data.pop("sign", "")
    sign_type = data.pop("sign_type", "RSA2")
    try:
        alipay = _get_alipay()
        verified = alipay.verify(data, sign)
    except Exception:
        verified = False

    if not verified:
        return PlainTextResponse("fail")

    out_trade_no = data.get("out_trade_no", "")
    trade_status = data.get("trade_status", "")

    if trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
        # 从数据库查订单（不依赖内存）
        order = db.query(PaymentOrder).filter(
            PaymentOrder.order_no == out_trade_no,
        ).with_for_update().first()
        if order and order.status != "paid":
            plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == order.plan_id).first()
            if plan:
                days = 365 if plan.plan_type == "yearly" else 30
                user = db.query(User).filter(User.id == order.user_id).first()
                if user and user.role != "premium":
                    _upgrade_user(db, user, plan, days)
                order.status = "paid"
                order.alipay_trade_no = data.get("trade_no", "")
                order.paid_at = _utcnow()
                db.commit()
        # 清理内存缓存
        _pending_orders.pop(out_trade_no, None)

    elif trade_status == "TRADE_CLOSED":
        # 用户在支付宝端取消了支付，标记订单为已关闭
        order = db.query(PaymentOrder).filter(
            PaymentOrder.order_no == out_trade_no,
        ).with_for_update().first()
        if order and order.status == "pending":
            order.status = "expired"
            db.commit()
        _pending_orders.pop(out_trade_no, None)

    return PlainTextResponse("success")
