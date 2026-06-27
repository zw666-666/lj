"""裁判文书相关模型"""
from datetime import datetime, timezone, date
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, JSON, Boolean, Float, ForeignKey, Index
from app.core.database import Base


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        Index("idx_cases_status_deleted", "processing_status", "is_deleted"),
        Index("idx_cases_category2", "case_category_2"),
        Index("idx_cases_court_level", "court_level"),
        Index("idx_cases_procedure", "trial_procedure"),
        Index("idx_cases_judgment_date", "judgment_date"),
        Index("idx_cases_title", "title"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_no = Column(String(100), unique=True)
    title = Column(String(500))
    court = Column(String(200))
    court_level = Column(String(20))          # basic / intermediate / high / supreme
    court_region = Column(String(100))
    judge_name = Column(String(100))
    trial_procedure = Column(String(20))      # first / second / retrial / supervision
    case_category_1 = Column(String(100))
    case_category_2 = Column(String(100))
    case_category_3 = Column(String(100))
    judgment_date = Column(Date)
    full_text = Column(Text)
    summary = Column(Text)
    ruling_abstract = Column(Text)
    tags = Column(JSON)
    processing_status = Column(
        String(20), default="pending"
    )  # pending / summarizing / classifying / extracting / linking / completed / failed
    confidence_score = Column(Float, default=0)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class DisputeFocus(Base):
    __tablename__ = "dispute_focuses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    focus_name = Column(String(300), nullable=False)
    plaintiff_claim = Column(Text)
    defendant_defense = Column(Text)
    court_finding = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LegalEntity(Base):
    __tablename__ = "legal_entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String(20), nullable=False)  # party / court / judge / article / rule / other
    entity_name = Column(String(300), nullable=False)
    entity_detail = Column(JSON)
    confidence = Column(Float, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LegalRule(Base):
    __tablename__ = "legal_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    rule_text = Column(Text, nullable=False)
    rule_type = Column(String(20))  # establish / extend / restrict / conflict / confirm
    related_article = Column(String(300))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CaseRelation(Base):
    __tablename__ = "case_relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    target_case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    relation_type = Column(String(20))  # similar / inherit / cite / cited_by / conflict / same_category
    relation_detail = Column(Text)
    confidence = Column(Float, default=0)
    is_confirmed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class JudgeProfile(Base):
    __tablename__ = "judge_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    judge_name = Column(String(100), unique=True, nullable=False)
    court = Column(String(200))
    division = Column(String(200))
    total_cases = Column(Integer, default=0)
    avg_duration_days = Column(Float)
    support_plaintiff_ratio = Column(Float)
    support_defendant_ratio = Column(Float)
    partial_support_ratio = Column(Float)
    appeal_reversal_ratio = Column(Float)
    reversed_by_superior_ratio = Column(Float)
    avg_opinion_length = Column(Integer)
    top_articles = Column(JSON)
    case_type_distribution = Column(JSON)
    style_tags = Column(JSON)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class ProcessingLog(Base):
    __tablename__ = "processing_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    stage = Column(String(20), nullable=False)   # summarizing / classifying / extracting / linking
    status = Column(String(20), nullable=False)  # processing / success / failed / retrying
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
