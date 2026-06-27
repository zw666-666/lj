"""短信验证码服务。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

SmsScene = Literal["register", "login", "bind"]


def _normalize_phone(phone: str) -> str:
    return "".join(ch for ch in (phone or "").strip() if ch.isdigit() or ch == "+")


def _is_valid_phone(phone: str) -> bool:
    phone = _normalize_phone(phone)
    return bool(phone) and bool(__import__("re").match(r"^1[3-9]\d{9}$", phone))


def _percent_encode(value: str) -> str:
    return urllib.parse.quote(str(value), safe="~")


@dataclass
class SmsSendResult:
    expires_in: int
    cooldown_seconds: int
    mock_code: Optional[str] = None


class SmsService:
    @classmethod
    def _missing_aliyun_fields(cls) -> list[str]:
        missing = []
        if not settings.SMS_ALIYUN_ACCESS_KEY_ID:
            missing.append("SMS_ALIYUN_ACCESS_KEY_ID")
        if not settings.SMS_ALIYUN_ACCESS_KEY_SECRET:
            missing.append("SMS_ALIYUN_ACCESS_KEY_SECRET")
        if not settings.SMS_ALIYUN_SIGN_NAME:
            missing.append("SMS_ALIYUN_SIGN_NAME")
        if not settings.SMS_ALIYUN_TEMPLATE_CODE:
            missing.append("SMS_ALIYUN_TEMPLATE_CODE")
        return missing

    @classmethod
    def _raise_missing_config(cls) -> None:
        missing = cls._missing_aliyun_fields()
        detail = "短信服务配置不完整"
        if missing:
            detail = f"{detail}，缺少：{', '.join(missing)}"
        raise HTTPException(status_code=500, detail=detail)

    @classmethod
    def normalize_phone(cls, phone: str) -> str:
        return _normalize_phone(phone)

    @classmethod
    def validate_phone(cls, phone: str) -> str:
        normalized = _normalize_phone(phone)
        if not _is_valid_phone(normalized):
            raise HTTPException(status_code=400, detail="手机号格式不正确")
        return normalized

    @classmethod
    def _redis(cls):
        return get_redis_client()

    @classmethod
    def _code_key(cls, scene: SmsScene, phone: str) -> str:
        return f"{settings.REDIS_PREFIX}:sms:code:{scene}:{phone}"

    @classmethod
    def _cooldown_key(cls, scene: SmsScene, phone: str) -> str:
        return f"{settings.REDIS_PREFIX}:sms:cooldown:{scene}:{phone}"

    @classmethod
    def _payload(cls, code: str) -> str:
        return json.dumps(
            {
                "code": code,
                "attempts": 0,
                "issued_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        )

    @classmethod
    def _parse_payload(cls, value: Optional[str]) -> Optional[dict]:
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return None

    @classmethod
    def send_code(cls, scene: SmsScene, phone: str) -> SmsSendResult:
        phone = cls.validate_phone(phone)
        redis_client = cls._redis()
        cooldown_key = cls._cooldown_key(scene, phone)
        if redis_client.exists(cooldown_key):
            ttl = redis_client.ttl(cooldown_key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"验证码发送过于频繁，请{max(1, ttl)}秒后再试",
            )

        code = f"{secrets.randbelow(1000000):06d}"
        code_key = cls._code_key(scene, phone)
        if cls._is_mock_provider():
            logger.info("[SMS MOCK] scene=%s phone=%s code=%s", scene, phone, code)
            redis_client.setex(code_key, settings.SMS_CODE_TTL_SECONDS, cls._payload(code))
            redis_client.setex(cooldown_key, settings.SMS_CODE_SEND_INTERVAL_SECONDS, "1")
            return SmsSendResult(
                expires_in=settings.SMS_CODE_TTL_SECONDS,
                cooldown_seconds=settings.SMS_CODE_SEND_INTERVAL_SECONDS,
                mock_code=code,
            )

        try:
            cls._send_aliyun_sms(phone, code)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"短信发送失败：{exc}")

        redis_client.setex(code_key, settings.SMS_CODE_TTL_SECONDS, cls._payload(code))
        redis_client.setex(cooldown_key, settings.SMS_CODE_SEND_INTERVAL_SECONDS, "1")
        return SmsSendResult(
            expires_in=settings.SMS_CODE_TTL_SECONDS,
            cooldown_seconds=settings.SMS_CODE_SEND_INTERVAL_SECONDS,
        )

    @classmethod
    def verify_code(cls, scene: SmsScene, phone: str, code: str) -> bool:
        phone = cls.validate_phone(phone)
        if not code or not str(code).strip():
            raise HTTPException(status_code=400, detail="验证码不能为空")

        redis_client = cls._redis()
        code_key = cls._code_key(scene, phone)
        raw = redis_client.get(code_key)
        payload = cls._parse_payload(raw)
        if not payload:
            raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")

        attempts = int(payload.get("attempts") or 0)
        if attempts >= settings.SMS_CODE_MAX_ATTEMPTS:
            redis_client.delete(code_key)
            raise HTTPException(status_code=400, detail="验证码已失效，请重新获取")

        if str(payload.get("code")) != str(code).strip():
            payload["attempts"] = attempts + 1
            redis_client.setex(code_key, settings.SMS_CODE_TTL_SECONDS, json.dumps(payload, ensure_ascii=False))
            remaining = max(0, settings.SMS_CODE_MAX_ATTEMPTS - payload["attempts"])
            raise HTTPException(status_code=400, detail=f"验证码错误，还可重试{remaining}次")

        redis_client.delete(code_key)
        return True

    @classmethod
    def _is_mock_provider(cls) -> bool:
        return settings.SMS_PROVIDER.lower() == "mock"

    @classmethod
    def _send_aliyun_sms(cls, phone: str, code: str) -> None:
        """通过自定义 SMS 网关发送短信"""
        sms_url = getattr(settings, "SMS_GATEWAY_URL", "")
        if not sms_url:
            raise HTTPException(status_code=500, detail="短信网关未配置")

        url = sms_url.replace("?to=", f"?to={phone}").replace("&to=", f"&to={phone}").replace("&code=", f"&code={code}")
        try:
            resp = httpx.get(url, timeout=10.0)
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail=f"短信发送失败：HTTP {resp.status_code}")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"短信发送失败：{exc}")

    @classmethod
    def _sign_aliyun_request(cls, method: str, params: dict) -> str:
        canonicalized = "&".join(
            f"{_percent_encode(k)}={_percent_encode(v)}"
            for k, v in sorted(params.items())
            if v is not None and v != ""
        )
        string_to_sign = f"{method.upper()}&%2F&" + _percent_encode(canonicalized)
        key = f"{settings.SMS_ALIYUN_ACCESS_KEY_SECRET}&".encode("utf-8")
        digest = hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()
        return base64.b64encode(digest).decode("utf-8")
