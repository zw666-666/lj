"""初始化订阅方案数据（仅开发/测试环境）"""
from app.core.database import SessionLocal
from app.models.subscription import SubscriptionPlan


DEFAULT_PLANS = [
    {
        "name": "月度会员",
        "plan_type": "monthly",
        "price_cents": 1200,  # ¥12.00/月
        "original_price_cents": None,
        "features": [
            "不限次数AI智能问答",
            "深度案件对比分析",
            "无限案例报告导出",
            "知识图谱深度探索",
            "法官画像深度分析",
        ],
    },
    {
        "name": "年度会员",
        "plan_type": "yearly",
        "price_cents": 12000,  # ¥120/年（10个月价格，省¥24）
        "original_price_cents": 14400,  # 12×1200
        "features": [
            "不限次数AI智能问答",
            "深度案件对比分析",
            "无限案例报告导出",
            "知识图谱深度探索",
            "法官画像深度分析",
            "优先AI处理队列",
        ],
    },
]


def seed_plans():
    """向数据库插入默认订阅方案（更新价格或新增方案）"""
    db = SessionLocal()
    try:
        for plan_data in DEFAULT_PLANS:
            existing = db.query(SubscriptionPlan).filter(
                SubscriptionPlan.plan_type == plan_data["plan_type"]
            ).first()
            if existing:
                # 更新价格
                existing.price_cents = plan_data["price_cents"]
                existing.original_price_cents = plan_data.get("original_price_cents")
                existing.name = plan_data["name"]
                existing.features = plan_data["features"]
            else:
                plan = SubscriptionPlan(**plan_data)
                db.add(plan)

        db.commit()
    finally:
        db.close()
