"""每日用量统计模型"""
from datetime import date
from sqlalchemy import Column, Integer, Date, ForeignKey, UniqueConstraint
from app.core.database import Base


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    usage_date = Column(Date, nullable=False, default=date.today)
    qa_count = Column(Integer, default=0, comment="当日问答次数")

    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uk_user_date"),
    )
