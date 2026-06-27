"""订阅、支付订单模型"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, ForeignKey, JSON
from app.core.database import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, comment="方案名称")
    plan_type = Column(Enum("monthly", "yearly"), nullable=False, comment="周期类型")
    price_cents = Column(Integer, nullable=False, comment="价格(分)")
    original_price_cents = Column(Integer, comment="原价(分),用于展示折扣")
    is_active = Column(Boolean, default=True)
    features = Column(JSON, comment="方案权益描述")
    created_at = Column(DateTime, default=datetime.utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    status = Column(Enum("active", "expired", "cancelled", "pending"), default="pending")
    started_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    auto_renew = Column(Boolean, default=False)
    cancelled_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("subscription_plans.id"), nullable=False)
    order_no = Column(String(64), unique=True, nullable=False, index=True, comment="商户订单号")
    alipay_trade_no = Column(String(64), comment="支付宝交易号")
    amount_cents = Column(Integer, nullable=False, comment="金额(分)")
    status = Column(Enum("pending", "paid", "expired", "refunded", "failed"), default="pending")
    payment_method = Column(String(20), default="alipay")
    paid_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
