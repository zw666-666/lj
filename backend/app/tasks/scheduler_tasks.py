"""定时任务：订阅过期检查、每日用量重置"""
from datetime import date, timedelta

from app.core.database import SessionLocal
from app.models.user import User
from app.models.subscription import Subscription
from app.models.usage import UsageDaily
from app.core.security import _utcnow
from app.tasks.celery_app import celery_app


if celery_app is not None:

    @celery_app.task(name="check_expired_subscriptions")
    def check_expired_subscriptions():
        """每小时检查过期的订阅，将对应用户降级为 normal"""
        db = SessionLocal()
        try:
            now = _utcnow()

            expired_subs = db.query(Subscription).filter(
                Subscription.status == "active",
                Subscription.expires_at < now,
            ).all()

            for sub in expired_subs:
                sub.status = "expired"

                # 检查用户是否有更新的有效订阅
                newer = db.query(Subscription).filter(
                    Subscription.user_id == sub.user_id,
                    Subscription.status == "active",
                    Subscription.expires_at >= now,
                ).first()

                if not newer:
                    user = db.query(User).filter(User.id == sub.user_id).first()
                    if user and user.role == "premium":
                        user.role = "normal"
                        user.subscription_expires_at = None

            db.commit()
            return {"expired_count": len(expired_subs)}
        finally:
            db.close()


    @celery_app.task(name="reset_daily_usage")
    def reset_daily_usage():
        """每日00:00清理前一天的用量记录"""
        db = SessionLocal()
        try:
            yesterday = date.today() - timedelta(days=1)
            deleted = db.query(UsageDaily).filter(
                UsageDaily.usage_date <= yesterday
            ).delete(synchronize_session=False)
            db.commit()
            return {"deleted_rows": deleted}
        finally:
            db.close()
