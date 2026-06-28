"""支付宝支付服务 —— 签名、验签、统一下单"""
import json
import base64
import uuid
from datetime import datetime
from urllib.parse import urlencode, parse_qs
from typing import Dict, Optional, Tuple

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

from app.core.config import settings


class AlipayService:
    """支付宝电脑网站支付（Page Pay）服务"""

    GATEWAY = "https://openapi.alipay.com/gateway.do"
    SANDBOX_GATEWAY = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
    FORMAT = "JSON"
    CHARSET = "utf-8"
    SIGN_TYPE = "RSA2"
    VERSION = "1.0"

    @classmethod
    def _gateway(cls) -> str:
        return cls.SANDBOX_GATEWAY if settings.ALIPAY_SANDBOX else cls.GATEWAY

    # ==================== 签名 ====================

    @classmethod
    def _build_sign_string(cls, params: Dict[str, str]) -> str:
        """构造待签名字符串（按key升序，排除sign）"""
        sorted_items = sorted(
            (k, v) for k, v in params.items()
            if v is not None and v != "" and k != "sign"
        )
        return "&".join(f"{k}={v}" for k, v in sorted_items)

    @classmethod
    def sign(cls, params: Dict[str, str]) -> str:
        """RSA2签名"""
        sign_string = cls._build_sign_string(params)
        private_key = load_pem_private_key(
            settings.ALIPAY_PRIVATE_KEY.encode("utf-8") if "-----BEGIN" in settings.ALIPAY_PRIVATE_KEY
            else f"-----BEGIN RSA PRIVATE KEY-----\n{settings.ALIPAY_PRIVATE_KEY}\n-----END RSA PRIVATE KEY-----".encode("utf-8"),
            password=None,
        )
        signature = private_key.sign(
            sign_string.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    @classmethod
    def verify(cls, params: Dict[str, str], signature: str) -> bool:
        """RSA2验签"""
        try:
            sign_string = cls._build_sign_string(params)
            public_key = load_pem_public_key(
                settings.ALIPAY_PUBLIC_KEY.encode("utf-8") if "-----BEGIN" in settings.ALIPAY_PUBLIC_KEY
                else f"-----BEGIN PUBLIC KEY-----\n{settings.ALIPAY_PUBLIC_KEY}\n-----END PUBLIC KEY-----".encode("utf-8"),
            )
            public_key.verify(
                base64.b64decode(signature),
                sign_string.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
            return True
        except Exception:
            return False

    # ==================== 统一下单 ====================

    @classmethod
    def generate_order_no(cls) -> str:
        """生成商户订单号"""
        now = datetime.utcnow()
        return f"LJ{now.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:8].upper()}"

    @classmethod
    def build_page_pay_url(
        cls,
        order_no: str,
        amount_cents: int,
        subject: str,
        return_url: Optional[str] = None,
        notify_url: Optional[str] = None,
    ) -> str:
        """构造支付宝电脑网站支付页面URL"""
        amount_yuan = f"{amount_cents / 100:.2f}"

        biz_content = json.dumps({
            "out_trade_no": order_no,
            "product_code": "FAST_INSTANT_TRADE_PAY",
            "total_amount": amount_yuan,
            "subject": subject,
            "timeout_express": "30m",
        }, ensure_ascii=False)

        params = {
            "app_id": settings.ALIPAY_APP_ID,
            "method": "alipay.trade.page.pay",
            "format": cls.FORMAT,
            "charset": cls.CHARSET,
            "sign_type": cls.SIGN_TYPE,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "version": cls.VERSION,
            "notify_url": notify_url or settings.ALIPAY_NOTIFY_URL,
            "return_url": return_url or settings.ALIPAY_RETURN_URL,
            "biz_content": biz_content,
        }

        params["sign"] = cls.sign(params)
        query_string = urlencode(params, quote_via=lambda s, *_: s)  # 支付宝要求不编码
        return f"{cls._gateway()}?{query_string}"

    # ==================== 通知处理 ====================

    @classmethod
    def verify_notify(cls, raw_body: bytes) -> Tuple[bool, Dict[str, str]]:
        """验证支付宝异步通知"""
        try:
            body_str = raw_body.decode("utf-8")
            params = {k: v[0] for k, v in parse_qs(body_str).items()}
            received_sign = params.pop("sign", "")
            sign_type = params.pop("sign_type", cls.SIGN_TYPE)

            if cls.verify(params, received_sign):
                return True, params
            return False, params
        except Exception:
            return False, {}
