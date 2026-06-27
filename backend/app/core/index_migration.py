"""给已有 SQLite 数据库补建索引和新增字段。"""
from sqlalchemy import text
from app.core.database import engine
from app.core.config import settings


def ensure_indexes():
    """检查并补建 cases 表上的搜索优化索引（幂等操作）。"""
    if "sqlite" not in settings.DATABASE_URL:
        return

    indexes = [
        ("idx_cases_status_deleted", "cases", "processing_status, is_deleted"),
        ("idx_cases_category2", "cases", "case_category_2"),
        ("idx_cases_court_level", "cases", "court_level"),
        ("idx_cases_procedure", "cases", "trial_procedure"),
        ("idx_cases_judgment_date", "cases", "judgment_date"),
        ("idx_cases_title", "cases", "title"),
    ]

    with engine.connect() as conn:
        for idx_name, table, cols in indexes:
            result = conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND name=:name"
                ),
                {"name": idx_name},
            ).fetchone()
            if not result:
                conn.execute(
                    text(f"CREATE INDEX {idx_name} ON {table} ({cols})")
                )
        conn.commit()


def ensure_columns():
    """检查并补建 users 表新增字段（幂等操作）。"""
    if "sqlite" not in settings.DATABASE_URL:
        return

    # users 表新增字段
    user_columns = [
        ("search_count", "INTEGER DEFAULT 0"),
        ("read_count", "INTEGER DEFAULT 0"),
        ("subscription_expires_at", "DATETIME"),
        ("lifetime_export_count", "INTEGER DEFAULT 0"),
    ]

    # user_activities 表新增字段
    activity_columns = [
        ("result_data", "JSON"),
    ]

    with engine.connect() as conn:
        for table, columns in [("users", user_columns), ("user_activities", activity_columns)]:
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
            }
            for col_name, col_def in columns:
                if col_name not in existing:
                    conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    )
        conn.commit()
