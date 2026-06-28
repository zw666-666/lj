"""应用配置"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "律镜 LawMirror"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 数据库
    DATABASE_URL: str = "mysql+pymysql://lvjing:lvjing_pass@localhost:3306/lvjing"

    # Redis
    REDIS_URL: str = "redis://:lj_redis_2024@localhost:6379/0"
    REDIS_PREFIX: str = "lvjing"

    # Elasticsearch
    ES_URL: str = "http://localhost:9200"

    # RabbitMQ
    RABBITMQ_URL: str = "amqp://lvjing:lvjing_mq_2024@localhost:5672//"

    # JWT
    JWT_SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # AI（DeepSeek）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_API_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # 支付宝
    ALIPAY_APP_ID: str = ""
    ALIPAY_PRIVATE_KEY: str = ""
    ALIPAY_PUBLIC_KEY: str = ""
    ALIPAY_NOTIFY_URL: str = ""
    ALIPAY_RETURN_URL: str = ""
    ALIPAY_SANDBOX: bool = True  # 沙箱模式
    ALIPAY_GATEWAY: str = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
    ALIPAY_CALLBACK_URL: str = ""
    FRONTEND_URL: str = "http://localhost:3000"
    PUBLIC_BASE_URL: str = ""

    # 短信验证码
    SMS_PROVIDER: str = "aliyun"  # aliyun / mock
    SMS_CODE_TTL_SECONDS: int = 300
    SMS_CODE_SEND_INTERVAL_SECONDS: int = 60
    SMS_CODE_MAX_ATTEMPTS: int = 5
    SMS_ALIYUN_ACCESS_KEY_ID: str = ""
    SMS_ALIYUN_ACCESS_KEY_SECRET: str = ""
    SMS_ALIYUN_SIGN_NAME: str = ""
    SMS_ALIYUN_TEMPLATE_CODE: str = ""
    SMS_ALIYUN_ENDPOINT: str = "https://dysmsapi.aliyuncs.com"
    SMS_GATEWAY_URL: str = ""  # 自定义短信网关

    model_config = {"env_file": (".env", "../.env"), "env_file_encoding": "utf-8", "extra": "ignore"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 将 SQLite 相对路径解析为 backend/ 目录下的绝对路径
        if self.DATABASE_URL.startswith("sqlite:///./"):
            # 找到 backend 目录（本文件在 backend/app/core/config.py）
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_name = self.DATABASE_URL.replace("sqlite:///./", "")
            self.DATABASE_URL = f"sqlite:///{os.path.join(backend_dir, db_name)}"


settings = Settings()

