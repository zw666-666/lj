"""Celery 应用配置（可选组件，不可用时不会阻断应用启动）"""
from celery import Celery
from app.core.config import settings

# Celery 是否可用（RabbitMQ/Redis 未部署时自动降级）
try:
    celery_app = Celery(
        "lvjing",
        broker=settings.RABBITMQ_URL,
        backend=settings.REDIS_URL.replace("/0", "/1"),
        include=["app.tasks.pipeline_tasks", "app.tasks.scheduler_tasks"],
    )

    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )

    # 定时任务配置
    celery_app.conf.beat_schedule = {
        "update-judge-profiles-daily": {
            "task": "app.tasks.pipeline_tasks.update_judge_profiles",
            "schedule": 86400.0,
        },
        "sync-es-index-hourly": {
            "task": "app.tasks.pipeline_tasks.sync_es_index",
            "schedule": 3600.0,
        },
        "check-expired-subscriptions-hourly": {
            "task": "check_expired_subscriptions",
            "schedule": 3600.0,
        },
        "reset-daily-usage-midnight": {
            "task": "reset_daily_usage",
            "schedule": 86400.0,
        },
    }
except Exception:
    # RabbitMQ 不可用时 celery_app 为 None
    celery_app = None
