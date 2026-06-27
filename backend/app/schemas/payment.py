"""支付相关 Pydantic Schema"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ----- 定价方案 -----
class PlanOut(BaseModel):
    id: int
    name: str
    plan_type: str  # monthly / yearly
    price_cents: int
    original_price_cents: Optional[int] = None
    features: Optional[list] = None

    model_config = {"from_attributes": True}


class PlanListResponse(BaseModel):
    plans: List[PlanOut]


# ----- 创建订单 -----
class CreateOrderRequest(BaseModel):
    plan_id: int = Field(..., description="订阅方案ID")


class CreateOrderResponse(BaseModel):
    order_no: str
    amount_cents: int
    pay_url: str = ""  # 支付宝支付页面URL（或二维码数据）
    qr_code: str = ""  # 二维码base64（备选方案）


# ----- 订单状态查询 -----
class OrderStatusResponse(BaseModel):
    order_no: str
    status: str  # pending / paid / expired / refunded / failed
    plan_name: str = ""
    amount_cents: int = 0
    paid_at: Optional[datetime] = None


# ----- 支付宝异步通知 -----
class AlipayNotifyParams(BaseModel):
    """支付宝异步通知参数（验签后解析）"""
    notify_time: Optional[str] = None
    notify_type: Optional[str] = None
    notify_id: Optional[str] = None
    app_id: Optional[str] = None
    out_trade_no: Optional[str] = None
    trade_no: Optional[str] = None
    trade_status: Optional[str] = None
    total_amount: Optional[str] = None
    buyer_id: Optional[str] = None
    buyer_logon_id: Optional[str] = None
    gmt_create: Optional[str] = None
    gmt_payment: Optional[str] = None
    sign: Optional[str] = None
    sign_type: Optional[str] = None


# ----- 用户订阅信息（嵌入 /me 响应） -----
class SubscriptionInfo(BaseModel):
    is_premium: bool = False
    plan_name: str = ""
    plan_type: str = ""
    expires_at: Optional[datetime] = None
    auto_renew: bool = False


# ----- 导出请求 -----
class ExportRequest(BaseModel):
    case_id: int = Field(..., description="案例ID")
    format: str = Field(default="pdf", description="导出格式: pdf / docx / txt")
    sections: List[str] = Field(default=["summary"], description="导出内容: summary / full_text / notes")
