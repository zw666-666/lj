"""用户内容模型：收藏、笔记、分组、问答、通知"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean, ForeignKey
from app.core.database import Base


class Favorite(Base):
    __tablename__ = "favorites"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    personal_tags = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    paragraph_ref = Column(String(100))
    entity_ref = Column(String(300))
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class CaseGroup(Base):
    __tablename__ = "case_groups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_name = Column(String(200), nullable=False)
    description = Column(Text)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaseGroupItem(Base):
    __tablename__ = "case_group_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("case_groups.id", ondelete="CASCADE"), nullable=False)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, default=0)


class QASession(Base):
    __tablename__ = "qa_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_title = Column(String(300))
    knowledge_scope = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class QAMessage(Base):
    __tablename__ = "qa_messages"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("qa_sessions.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(10), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    citations = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(300), nullable=False)
    content = Column(Text)
    notify_type = Column(String(20), nullable=False)  # processing_done / new_case / new_judgment / system
    is_read = Column(Boolean, default=False)
    ref_id = Column(Integer)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserActivity(Base):
    """用户行为日志：检索、阅读历史"""
    __tablename__ = "user_activities"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    activity_type = Column(String(10), nullable=False)  # search / read
    detail = Column(Text)          # 检索词 或 案例标题
    case_id = Column(Integer)      # 阅读时有案例 ID
    result_data = Column(JSON)     # 检索结果概要：{ total, cases: [{id, title, case_no}] }
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
