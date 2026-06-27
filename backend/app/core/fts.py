"""SQLite FTS5 全文搜索初始化。
创建 cases_fts 虚拟表及自动同步触发器，用于替代 LIKE '%keyword%' 全表扫描。
"""
from sqlalchemy import text
from app.core.database import engine
from app.core.config import settings


def init_fts5():
    """创建 FTS5 虚拟表和触发器（仅 SQLite，幂等操作）。"""
    if "sqlite" not in settings.DATABASE_URL:
        return

    with engine.connect() as conn:
        # 1. 创建 external-content FTS5 表（指向真实 cases 表）
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS cases_fts USING fts5(
                full_text,
                content='cases',
                content_rowid='id'
            )
        """))

        # 2. INSERT 触发器：新增案例时自动加入 FTS5
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS cases_fts_ai AFTER INSERT ON cases BEGIN
                INSERT INTO cases_fts(rowid, full_text) VALUES (new.id, new.full_text);
            END
        """))

        # 3. DELETE 触发器：删除案例时自动从 FTS5 移除
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS cases_fts_ad AFTER DELETE ON cases BEGIN
                INSERT INTO cases_fts(cases_fts, rowid, full_text) VALUES('delete', old.id, old.full_text);
            END
        """))

        # 4. UPDATE 触发器：更新案例时重新同步 FTS5
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS cases_fts_au AFTER UPDATE ON cases BEGIN
                INSERT INTO cases_fts(cases_fts, rowid, full_text) VALUES('delete', old.id, old.full_text);
                INSERT INTO cases_fts(rowid, full_text) VALUES (new.id, new.full_text);
            END
        """))

        # 5. 从已有数据填充 FTS5（幂等：INSERT OR IGNORE）
        conn.execute(text("""
            INSERT OR IGNORE INTO cases_fts(rowid, full_text)
            SELECT id, full_text FROM cases WHERE full_text IS NOT NULL
        """))
        conn.commit()
