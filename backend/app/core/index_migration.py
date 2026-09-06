"""给已有数据库补建索引和新增字段。"""
import re

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


def ensure_case_status_support():
    """为旧版 MySQL 枚举补充 ``unpublished`` 下架状态。

    ``CREATE TABLE IF NOT EXISTS`` 不会修改已经存在的表。早期生产库的
    ``cases.processing_status`` 枚举未包含 ``unpublished``，管理员下架时会
    因 MySQL 拒绝该值而导致整个请求失败。仅当字段确实是缺少该值的枚举时
    执行一次 ALTER，其他数据库及已升级的数据库不受影响。
    """
    if not settings.DATABASE_URL.startswith(("mysql", "mariadb")):
        return

    with engine.begin() as conn:
        column = conn.execute(
            text(
                """
                SELECT DATA_TYPE, COLUMN_TYPE
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'cases'
                  AND COLUMN_NAME = 'processing_status'
                """
            )
        ).mappings().first()

        if not column or (column["DATA_TYPE"] or "").lower() != "enum":
            return

        status_values = re.findall(r"'((?:[^'\\]|\\.)*)'", column["COLUMN_TYPE"] or "")
        if "unpublished" in status_values:
            return

        status_values.append("unpublished")
        def quote_enum_value(value: str) -> str:
            escaped = value.replace("\\", "\\\\").replace("'", "\\'")
            return f"'{escaped}'"

        enum_values = ", ".join(quote_enum_value(value) for value in status_values)
        conn.execute(
            text(
                "ALTER TABLE cases MODIFY COLUMN processing_status "
                f"ENUM({enum_values}) NULL DEFAULT 'pending'"
            )
        )
