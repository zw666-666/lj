"""律镜 LawMirror — FastAPI 应用入口"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app.api import auth, users, search, cases, profiles, compare, qa, workspace, admin, payment, alipay_payment


async def _scheduler_loop():
    """简易后台调度器（Celery 不可用时的降级方案）"""
    # 等待应用启动完成
    await asyncio.sleep(30)

    last_reset_day = None
    while True:
        try:
            now = __import__("datetime").datetime.utcnow()
            today = now.date()

            # 每天执行一次用量重置
            if last_reset_day is None or last_reset_day < today:
                try:
                    from app.tasks.scheduler_tasks import check_expired_subscriptions, reset_daily_usage
                    check_expired_subscriptions()
                    reset_daily_usage()
                    last_reset_day = today
                except Exception:
                    pass

            # 每小时检查过期订阅
            try:
                from app.tasks.scheduler_tasks import check_expired_subscriptions
                check_expired_subscriptions()
            except Exception:
                pass

        except Exception:
            pass

        await asyncio.sleep(3600)  # 每小时


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 —— 开发模式下不强制数据库连接"""
    try:
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass  # 开发模式，数据库不可用时跳过

    # 初始化 SQLite FTS5 全文搜索（幂等操作）
    try:
        from app.core.fts import init_fts5
        init_fts5()
    except Exception:
        pass

    # 补建索引和新增字段（幂等操作）
    try:
        from app.core.index_migration import ensure_indexes, ensure_columns
        ensure_indexes()
        ensure_columns()
    except Exception:
        pass

    # 初始化订阅方案（首次运行时填充默认数据）
    try:
        from app.core.seed_plans import seed_plans
        seed_plans()
    except Exception:
        pass

    # 启动后台调度器（不依赖 Celery）
    scheduler_task = asyncio.create_task(_scheduler_loop())

    yield

    # 清理
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass



app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI 驱动的智能类案检索与裁判规则分析平台",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:80",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:80",
        "http://192.168.10.27:3000",
        "http://192.168.10.27:80",
        "http://120.27.143.225",
        "http://120.27.143.225:80",
    ],
    allow_origin_regex=r"^https?://([a-zA-Z0-9-]+\.)*[a-zA-Z0-9-]+(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(search.router)
app.include_router(cases.router)
app.include_router(profiles.router)
app.include_router(compare.router)
app.include_router(qa.router)
app.include_router(workspace.router)
app.include_router(admin.router)
app.include_router(payment.router)
app.include_router(alipay_payment.router)


@app.get("/api/health")
def health_check():
    """健康检查"""
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.APP_VERSION}
