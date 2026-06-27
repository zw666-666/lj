"""用量统计服务 —— 免费用户每日限制检查与递增"""
from datetime import date
from typing import Tuple

from sqlalchemy.orm import Session
from app.models.usage import UsageDaily


# 免费用户每日限制
FREE_QA_LIMIT = 5


class UsageService:

    @classmethod
    def check_and_increment_qa(cls, user_id: int, role: str, db: Session) -> Tuple[bool, int, int]:
        """检查QA次数，若未超限则递增。返回 (allowed, current_count, limit)"""
        # 会员/管理员不限
        if role in ("premium", "admin"):
            return True, -1, -1  # -1 表示无限制

        today = date.today()
        record = db.query(UsageDaily).filter(
            UsageDaily.user_id == user_id,
            UsageDaily.usage_date == today,
        ).first()

        current = record.qa_count if record else 0

        if current >= FREE_QA_LIMIT:
            return False, current, FREE_QA_LIMIT

        # 递增
        if record:
            record.qa_count = current + 1
        else:
            record = UsageDaily(user_id=user_id, usage_date=today, qa_count=1)
            db.add(record)
        db.flush()

        return True, current + 1, FREE_QA_LIMIT

    @classmethod
    def get_remaining_qa(cls, user_id: int, role: str, db: Session) -> int:
        """获取今日剩余QA次数（会员返回-1表示无限）"""
        if role in ("premium", "admin"):
            return -1

        today = date.today()
        record = db.query(UsageDaily).filter(
            UsageDaily.user_id == user_id,
            UsageDaily.usage_date == today,
        ).first()

        current = record.qa_count if record else 0
        return max(0, FREE_QA_LIMIT - current)

    @classmethod
    def reset_daily_usage(cls, db: Session) -> int:
        """清理前一天的用量记录，返回清理行数"""
        yesterday = date.today()
        # 删除所有非今天的记录（定时任务调用）
        deleted = db.query(UsageDaily).filter(
            UsageDaily.usage_date < yesterday
        ).delete()
        db.commit()
        return deleted
