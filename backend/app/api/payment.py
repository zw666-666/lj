"""支付接口 —— 创建订单、支付宝回调、订单查询"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, _utcnow
from app.models.user import User
from app.models.subscription import SubscriptionPlan, Subscription, PaymentOrder
from app.schemas.payment import (
    PlanListResponse, PlanOut, CreateOrderRequest, CreateOrderResponse,
    OrderStatusResponse,
)
from app.services.payment_service import AlipayService

router = APIRouter(prefix="/api/payment", tags=["支付"])


# ===================== 方案查询 =====================

@router.get("/plans", response_model=PlanListResponse)
def get_plans(db: Session = Depends(get_db)):
    """获取所有有效的订阅方案"""
    plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).all()
    return PlanListResponse(plans=[PlanOut.model_validate(p) for p in plans])


# ===================== 创建订单 =====================

@router.post("/create-order", response_model=CreateOrderResponse)
def create_order(
    req: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建支付宝支付订单，返回支付页面URL"""
    plan = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.id == req.plan_id,
        SubscriptionPlan.is_active == True,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="方案不存在")

    order_no = AlipayService.generate_order_no()

    order = PaymentOrder(
        user_id=current_user.id,
        plan_id=plan.id,
        order_no=order_no,
        amount_cents=plan.price_cents,
        status="pending",
    )
    db.add(order)
    db.commit()

    # 构造支付宝支付URL
    pay_url = AlipayService.build_page_pay_url(
        order_no=order_no,
        amount_cents=plan.price_cents,
        subject=f"律镜会员 - {plan.name}",
    )

    return CreateOrderResponse(
        order_no=order_no,
        amount_cents=plan.price_cents,
        pay_url=pay_url,
    )


# ===================== 订单状态查询 =====================

@router.get("/order/{order_no}", response_model=OrderStatusResponse)
def query_order(
    order_no: str,
    db: Session = Depends(get_db),
):
    """查询支付订单状态（out_trade_no 全局唯一，无需登录校验）"""
    order = db.query(PaymentOrder).filter(PaymentOrder.order_no == order_no).first()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 如果订单还 pending，主动向支付宝查询真实状态
    if order.status == "pending":
        try:
            from app.api.alipay_payment import _get_alipay
            alipay = _get_alipay()
            result = alipay.api_alipay_trade_query(out_trade_no=order_no)
            trade_status = result.get("trade_status", "")
            if result.get("code") == "10000" and trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"):
                plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == order.plan_id).first()
                if plan:
                    from datetime import timedelta
                    from app.core.security import _utcnow
                    days = 365 if plan.plan_type == "yearly" else 30
                    user = db.query(User).filter(User.id == order.user_id).first()
                    if user and user.role != "premium":
                        now = _utcnow()
                        if user.subscription_expires_at and user.subscription_expires_at > now:
                            user.subscription_expires_at = user.subscription_expires_at + timedelta(days=days)
                        else:
                            user.subscription_expires_at = now + timedelta(days=days)
                        user.role = "premium"
                        sub = Subscription(
                            user_id=user.id, plan_id=plan.id, status="active",
                            started_at=now, expires_at=user.subscription_expires_at,
                        )
                        db.add(sub)
                order.status = "paid"
                order.alipay_trade_no = result.get("trade_no", "")
                order.paid_at = _utcnow()
                db.commit()
            elif trade_status == "TRADE_CLOSED":
                order.status = "expired"
                db.commit()
        except Exception:
            pass  # 支付宝查询失败时返回 DB 中的当前状态

    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == order.plan_id).first()
    return OrderStatusResponse(
        order_no=order.order_no,
        status=order.status,
        plan_name=plan.name if plan else "",
        amount_cents=order.amount_cents,
        paid_at=order.paid_at,
    )


# ===================== 支付宝同步回跳（GET） =====================

@router.get("/return", response_class=HTMLResponse)
def alipay_return():
    """支付宝支付完成后浏览器回跳——展示一个简单的跳转页面"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html><head><meta charset="utf-8"><title>支付完成</title></head>
    <body style="text-align:center;padding-top:60px;font-family:sans-serif;">
    <h2>支付处理中...</h2>
    <p>请稍候，正在确认支付结果</p>
    <script>
      const params = new URLSearchParams(window.location.search);
      const orderNo = params.get('out_trade_no') || '';
      if (orderNo) {
        window.location.href = '/payment-result?order_no=' + encodeURIComponent(orderNo);
      } else {
        window.location.href = '/payment-result';
      }
    </script>
    </body></html>""", status_code=200)


# ===================== 支付宝异步通知（POST） =====================

@router.post("/notify", response_class=PlainTextResponse)
async def alipay_notify(request: Request, db: Session = Depends(get_db)):
    """支付宝异步通知回调 —— 验证签名并激活订阅"""
    raw_body = await request.body()
    valid, params = AlipayService.verify_notify(raw_body)

    if not valid:
        return "fail"

    out_trade_no = params.get("out_trade_no", "")
    trade_no = params.get("trade_no", "")
    trade_status = params.get("trade_status", "")

    # 使用行锁防止并发处理
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == out_trade_no,
    ).with_for_update().first()

    if not order:
        return "fail"

    if trade_status == "TRADE_SUCCESS" and order.status != "paid":
        order.status = "paid"
        order.alipay_trade_no = trade_no
        order.paid_at = _utcnow()

        # 查找方案
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == order.plan_id).first()
        if plan:
            days = 30 if plan.plan_type == "monthly" else 365
            now = _utcnow()

            # 如果用户已有有效订阅，从其到期日开始续期
            existing = db.query(Subscription).filter(
                Subscription.user_id == order.user_id,
                Subscription.status == "active",
                Subscription.expires_at > now,
            ).first()

            if existing:
                start = existing.expires_at
            else:
                start = now

            expires = start + timedelta(days=days)

            # 创建/更新订阅
            sub = Subscription(
                user_id=order.user_id,
                plan_id=plan.id,
                status="active",
                started_at=now,
                expires_at=expires,
            )
            db.add(sub)

            # 更新用户角色和到期时间
            user = db.query(User).filter(User.id == order.user_id).first()
            if user:
                user.role = "premium"
                user.subscription_expires_at = expires

        db.commit()
        return "success"

    db.commit()
    return "success"
